#!/usr/bin/env python3
##
## pcc.py
## PIGS C compiler
##

import sys, argparse, re, collections
from pathlib import PurePath, Path

from pycparser import c_ast
from pycparser.c_parser import CParser
from pycparser.plyparser import ParseError

SCR0     = 'v0'                             ## General purpose (scratch) register
ARG_REGS = ('v1', 'v2', 'v3')               ## Function argument register (ARG0 ... ARG2)

class PccError(Exception):
    def __init__(self, node, message):
        super().__init__(message)
        self.node = node

## ---------------------------------------------------------------------------

class AsmVar:
    def __init__(self, var_sym=None):
        self.vm_var_id = None               ## None (unbound) or str "v0" ... "v149"
        self.var_sym = var_sym              ## VmVariableSymbol var_sym, 1:1 relationship
        self.unbound_id = None              ## str, fallback-id for unbound variables

    def format_decl_comment(self, c_sources):
        var_sym = self.var_sym
        coord = var_sym.decl_node.coord
        filename, row = c_sources.map_coord(coord.line)
        fqname = var_sym.cname
        if var_sym.context_function is not None:
            fqname = f'{var_sym.context_function.func_name}.{fqname}'
        return f'; {self!s: >3}: ' \
               f'{PurePath(filename).name}:{row}:{coord.column}: ' \
               f'{var_sym.ctype} {fqname}'

    def bind(self, vm_var_nr):
        self.vm_var_id = f'v{vm_var_nr}'

    _unbound_counter = 0
    def __str__(self):
        if self.vm_var_id is not None:
            return self.vm_var_id
        elif self.unbound_id is None:
            AsmVar._unbound_counter += 1
            self.unbound_id = f'<UNBOUND_VARIABLE_{AsmVar._unbound_counter}>'
        return self.unbound_id

class AsmStatement:
    def __init__(self, comment=None):
        self.comment = comment              ## None or str, optional comment

    def format_statement(self):
        raise NotImplementedError()

class AsmTag(AsmStatement):
    def __init__(self):
        super().__init__()
        self.vm_tag_id = None               ## None (unbound) or str "1", "2", ..., any unique positive integer
        self.unbound_id = None              ## str, fallback-id for unbound TAG labels

    def format_statement(self):
        return f'TAG {self}'

    def bind(self, vm_tag_id):
        self.vm_tag_id = str(vm_tag_id)

    _unbound_counter = 0
    def __str__(self):
        if self.vm_tag_id is not None:
            return self.vm_tag_id
        elif self.unbound_id is None:
            AsmTag._unbound_counter += 1
            self.unbound_id = f'<UNBOUND_LABEL_{AsmTag._unbound_counter}>'
        return self.unbound_id

class AsmCmd(AsmStatement):
    def __init__(self, instr, args, comment):
        super().__init__(comment=comment)
        self.instr = instr                  ## str, uppercase assembly language instruction
        self.args = args                    ## list(arg), command's arguments of type int, str, AsmVar or AsmTag

    def format_statement(self):
        return f'    {self.instr: <5} {" ".join([str(arg) for arg in self.args])}'

    @staticmethod
    def tag_instr_idx(instr):
        try:
            return ('TAG', 'CALL', 'JMP', 'JNZ', 'JZ', 'JP', 'JM').index(instr)
        except ValueError:
            return -1

class AsmBranchCmd(AsmCmd):
    pass

class AsmBuffer:
    def __init__(self):
        self.stmt_buf = []                  ## list(AsmStatement asm_stmt)

    def __call__(self, instr, *args, comment=None):
        instr = instr.upper()
        tag_instr_idx = AsmCmd.tag_instr_idx(instr)
        if tag_instr_idx < 0:               ## any instruction that doesn't expect a single TAG label argument
            asm_stmt = AsmCmd(instr, list(args), comment)
        elif len(args) != 1 or not isinstance(args[0], AsmTag):
            raise Exception(f'internal error: {instr} instruction expects a single AsmTag argument, ' \
                f'found: "{" ".join([str(arg) for arg in args])}"')
        elif tag_instr_idx == 0:            ## TAG <label> instruction (use AsmTag <label> as statement object)
            asm_stmt = args[0]
            if comment is not None:
                asm_stmt.comment = comment
        else:                               ## BRANCH <label> instruction (BRANCH one of JMP, JNZ, ...)
            asm_stmt = AsmBranchCmd(instr, list(args), comment)
        self.stmt_buf.append(asm_stmt)

    def extend(self, asm_buffer):
        self.stmt_buf.extend(asm_buffer.stmt_buf)

    def replace_instruction(self, find_instr, replace_instr):
        for asm_cmd in self.stmt_buf:
            if isinstance(asm_cmd, AsmCmd) and asm_cmd.instr == find_instr:
                asm_cmd.instr = replace_instr

    def _replace_tag(self, find_tag, replace_tag):
        for asm_cmd in self.stmt_buf:
            if isinstance(asm_cmd, AsmBranchCmd) and asm_cmd.args[0] is find_tag:
                asm_cmd.args[0] = replace_tag

    def reduce(self):
        in_buf = self.stmt_buf
        out_buf = [in_buf[0]]
        for curr_stmt in in_buf[1:]:
            prev_stmt = out_buf[-1]
            if isinstance(prev_stmt, AsmCmd) and isinstance(curr_stmt, AsmCmd):
                if prev_stmt.instr == 'RET' and curr_stmt.instr == 'RET':
                    ## "RET + <RET>" => drop "RET", keep "<RET>"
                    continue
                elif prev_stmt.instr == 'JMP' and curr_stmt.instr == 'JMP':
                    ## "JMP X + <JMP Y>" => drop "JMP Y", keep "<JMP X>"
                    continue
                elif prev_stmt.instr == 'STA' and curr_stmt.instr == 'LDA' and prev_stmt.args[0] == curr_stmt.args[0]:
                    ## "STA X + <LDA X>" => drop "<LDA Y>", keep "STA X"
                    continue
            elif isinstance(prev_stmt, AsmTag) and isinstance(curr_stmt, AsmTag):
                ## "TAG X + <TAG Y>" => replace all uses of "Y" with "X", keep "TAG X", drop "TAG Y"
                self._replace_tag(curr_stmt, prev_stmt)
                continue
            elif isinstance(prev_stmt, AsmTag) and isinstance(curr_stmt, AsmCmd) and curr_stmt.instr == 'JMP':
                if len(out_buf) > 2 and isinstance(out_buf[-2], AsmCmd) and out_buf[-2].instr == 'JMP':
                    ## "JMP Z + TAG X + <JMP Y>" => replace all uses of "X" with "Y", drop both "TAG X" and "<JMP Y>"
                    self._replace_tag(prev_stmt, curr_stmt.args[0])
                    del out_buf[-1]
                    continue
                else:
                    ## "TAG X + <JMP Y>" => replace all uses of "X" with "Y", drop "TAG X", keep "<JMP Y>"
                    self._replace_tag(prev_stmt, curr_stmt.args[0])
                    out_buf[-1] = curr_stmt
                    continue
            elif isinstance(prev_stmt, AsmCmd) and isinstance(curr_stmt, AsmTag):
                if prev_stmt.instr == 'JMP' and prev_stmt.args[0] == curr_stmt:
                    ## "JMP X + <TAG X>" => drop "JMP X", keep "<TAG X>"
                    out_buf[-1] = curr_stmt
                    continue
            out_buf.append(curr_stmt)
        self.stmt_buf = out_buf

    def drop_unused_tags(self, tag_use_count):
        for asm_stmt in self.stmt_buf:
            if isinstance(asm_stmt, AsmTag) and asm_stmt not in tag_use_count:
                tag_use_count[asm_stmt] = 0
            elif isinstance(asm_stmt, AsmBranchCmd):
                asm_tag = asm_stmt.args[0]
                if asm_tag not in tag_use_count:
                    tag_use_count[asm_tag] = 1
                else:
                    tag_use_count[asm_tag] += 1
        out_buf = []
        for asm_stmt in self.stmt_buf:
            if isinstance(asm_stmt, AsmTag) and tag_use_count[asm_stmt] == 0:
                continue    ## drop TAG-commands of tags that are not used in any branch-command
            out_buf.append(asm_stmt)
        self.stmt_buf = out_buf

    def bind_tags(self, tag_id_offset):
        tag_counter = 0
        for asm_tag in self.stmt_buf:
            if isinstance(asm_tag, AsmTag):
                asm_tag.bind(tag_id_offset + tag_counter)
                tag_counter += 1
        return tag_counter

    def collect_vm_variables(self, global_asm_vars, local_asm_vars):
        for asm_cmd in self.stmt_buf:
            if isinstance(asm_cmd, AsmCmd):
                for asm_var in asm_cmd.args:
                    if isinstance(asm_var, AsmVar):
                        if asm_var.var_sym.context_function is None:
                            global_asm_vars[asm_var] = True
                        else:
                            local_asm_vars[asm_var] = True
        
    def format_statements(self, use_comments):
        asm_lines = []
        for asm_stmt in self.stmt_buf:
            asm_line = asm_stmt.format_statement()
            if use_comments and asm_stmt.comment is not None:
                asm_line = f'{asm_line: <24}; {asm_stmt.comment}'
            asm_lines.append(asm_line)
        return asm_lines

## ---------------------------------------------------------------------------

class Function:
    def __init__(self, decl_node, is_vm_function):
        arg_ctypes = []
        func_args = decl_node.type.args
        if func_args is not None and not (len(func_args.params) == 1 and
                self._parse_ctype(func_args.params[0].type, accept_void=True, accept_uint=is_vm_function) == 'void'):
            for arg in func_args.params:
                arg_ctypes.append(self._parse_ctype(arg.type, accept_uint=is_vm_function))
        self.decl_node = decl_node
        self.func_name = decl_node.name
        self.ret_ctype = self._parse_ctype(decl_node.type.type, accept_void=True, accept_uint=is_vm_function)
        self.arg_ctypes = arg_ctypes
        self.arg_count = len(arg_ctypes)
        self.has_return = self.ret_ctype != 'void'

    def decl_str(self):
        return f'{self.ret_ctype} {self.func_name}({", ".join(self.arg_ctypes)})'

    def matches(self, other):
        return type(self) is type(other) and \
               self.arg_ctypes == other.arg_ctypes and \
               self.ret_ctype == other.ret_ctype

    def _parse_ctype(self, node, accept_void=False, accept_uint=False):
        if isinstance(node.type, c_ast.IdentifierType):
            type_names = node.type.names
            if len(type_names) == 1:
                type_name = type_names[0]
                if type_name in ('int', 'long'):
                    return type_name
                elif accept_void and type_name == 'void':
                    return type_name
                elif accept_uint and type_name == 'unsigned':
                    return type_name
            elif len(type_names) == 2:
                if accept_uint and type_names[0] == 'unsigned' and type_names[1] in ('int', 'long'):
                    return ' '.join(type_names)
            raise PccError(node.type, f'unsupported type "{" ".join(type_names)}"')
        raise PccError(node.type, 'unsupported type')

class VmApiFunction(Function):
    VM_FUNCTION_INSTR = {
        'gpioSetMode':                  'MODES',    ## Basic commands
        'gpioGetMode':                  'MODEG',
        'gpioSetPullUpDown':            'PUD',
        'gpioRead':                     'READ',
        'gpioWrite':                    'WRITE',
        'gpioPWM':                      'PWM',      ## PWM commands
        'gpioSetPWMfrequency':          'PFS',
        'gpioSetPWMrange':              'PRS',
        'gpioGetPWMdutycycle':          'GDC',
        'gpioGetPWMfrequency':          'PFG',
        'gpioGetPWMrange':              'PRG',
        'gpioGetPWMrealRange':          'PRRG',
        'gpioServo':                    'SERVO',    ## Servo commands
        'gpioGetServoPulsewidth':       'GPW',
        'gpioTrigger':                  'TRIG',     ## Intermediate commands
        'gpioSetWatchdog':              'WDOG',
        'gpioRead_Bits_0_31':           'BR1',
        'gpioRead_Bits_32_53':          'BR2',
        'gpioWrite_Bits_0_31_Clear':    'BC1',
        'gpioWrite_Bits_32_53_Clear':   'BC2',
        'gpioWrite_Bits_0_31_Set':      'BS1',
        'gpioWrite_Bits_32_53_Set':     'BS2',
        'gpioNotifyOpen':               'NO',       ## Advanced commands
        'gpioNotifyClose':              'NC',
        'gpioNotifyBegin':              'NB',
        'gpioNotifyPause':              'NP',
        'gpioHardwareClock':            'HC',
        'gpioHardwarePWM':              'HP',
        'gpioGlitchFilter':             'FG',
        'gpioNoiseFilter':              'FN',
        'gpioSetPad':                   'PADS',
        'gpioGetPad':                   'PADG',
        'eventMonitor':                 'EVM',      ## Event commands
        'eventTrigger':                 'EVT',
        'i2cOpen':                      'I2CO',     ## I2C commands
        'i2cClose':                     'I2CC',
        'i2cWriteQuick':                'I2CWQ',
        'i2cReadByte':                  'I2CRS',
        'i2cWriteByte':                 'I2CWS',
        'i2cReadByteData':              'I2CRB',
        'i2cWriteByteData':             'I2CWB',
        'i2cReadWordData':              'I2CRW',
        'i2cWriteWordData':             'I2CWW',
        'i2cProcessCall':               'I2CPC',
        'gpioHardwareRevision':         'HWVER',    ## Utility commands
        'gpioDelay_us':                 'MICS',
        'gpioDelay_ms':                 'MILS',
        'gpioVersion':                  'PIGPV',
        'gpioTick':                     'TICK',
        'gpioCfgGetInternals':          'CGI',      ## Configuration commands
        'gpioCfgSetInternals':          'CSI',
        'gpioWait':                     'WAIT',     ## Script-exclusive commands
        'eventWait':                    'EVTWT',
        'exit':                         'HALT' }

    def __init__(self, decl_node):
        super().__init__(decl_node, True)
        if self.func_name not in self.VM_FUNCTION_INSTR:
            raise PccError(decl_node, f'undefined VM function "{self.func_name}"')
        self.vm_func_instr = self.VM_FUNCTION_INSTR[self.func_name]
        self.map_argument = getattr(self, f'_map_argument_{self.func_name}', self._map_argument_default)

    def _map_argument_default(self, node, i_arg, const_arg):
        return const_arg

    def _map_argument_gpioSetPullUpDown(self, node, i_arg, const_arg):
        if i_arg == 1:
            ## int gpioSetPullUpDown(unsigned gpio, unsigned pud), 2nd argument "pud":
            ##   index    | 0          | 1           | 2
            ##   vm_api.h | PI_PUD_OFF | PI_PUD_DOWN | PI_PUD_UP
            ##   PUD g p  | "O"        | "D"         | "U"
            if const_arg is None:
                raise PccError(node, f'{self.decl_str()}: compile-time constant required for 2nd argument')
            const_int = int(const_arg, 0)
            if const_int >= 0 and const_int <= 2:
                const_arg = 'ODU'[const_int]
        return const_arg

    def _map_argument_gpioSetMode(self, node, i_arg, const_arg):
        if i_arg == 1:
            ## int gpioSetMode(unsigned gpio, unsigned mode), 2nd argument "mode":
            ##   index     | 0        | 1         | 2       | 3       | 4       | 5       | 6       | 7
            ##   vm_api.h  | PI_INPUT | PI_OUTPUT | PI_ALT5 | PI_ALT4 | PI_ALT0 | PI_ALT1 | PI_ALT2 | PI_ALT3
            ##   MODES g m | "R"      | "W"       | "5"     | "4"     | "0"     | "1"     | "2"     | "3"
            if const_arg is None:
                raise PccError(node, f'{self.decl_str()}: compile-time constant required for 2nd argument')
            const_int = int(const_arg, 0)
            if const_int >= 0 and const_int <= 7:
                const_arg = 'RW540123'[const_int]
        return const_arg

class UserDefFunction(Function):
    def __init__(self, decl_node):
        super().__init__(decl_node, False)
        if self.func_name == 'main':
            ## check main() function prototype constraints
            if self.has_return:
                raise PccError(decl_node, 'return type other than "void" is not supported for main()')
            elif self.arg_count > 0:
                raise PccError(decl_node, 'function arguments are not supported for main()')
        self.impl_node = None           ## None or c_ast.FuncDef, function implementation's AST node
        self.caller = set()             ## set(str func_name), set of calling function names
        self.asm_tag = AsmTag()         ## AsmTag, str() expands to function entry point's TAG
        self.asm_buf = AsmBuffer()      ## AsmBuffer, function implementation's statement buffer
        self.arg_vars = [               ## list(AsmVar), function argument VM variables
            AsmVar() for i in range(self.arg_count)]
        self.static_asm_tags = {}       ## dict(str tag_label: AsmTag asm_tag), user-defined static tags

## ---------------------------------------------------------------------------

class AbstractSymbol:
    def __init__(self, cname):
        self.cname = cname              ## str cname, symbol's C name in scope

    def asm_repr(self):                 ## returns str, AsmVar or AsmTag, only types
        raise NotImplementedError()     ## that properly expand themselves with str()

class EnumSymbol(AbstractSymbol):
    def __init__(self, cname, const_value):
        super().__init__(cname)
        self.const_value = const_value

    def asm_repr(self):                 ## str const_value, integer represented as str
        return self.const_value

class VariableSymbol(AbstractSymbol):
    def __init__(self, ctype, cname):
        super().__init__(cname)
        self.ctype = ctype

class VmVariableSymbol(VariableSymbol):
    def __init__(self, ctype, cname, asm_var, decl_node, context_function):
        super().__init__(ctype, cname)
        if asm_var is None:
            self.asm_var = AsmVar(var_sym=self)
        else:
            if asm_var.var_sym is not None:
                raise Exception('internal error: AsmVar is already bound to a VariableSymbol')
            asm_var.var_sym = self
            self.asm_var = asm_var
        self.decl_node = decl_node
        self.context_function = context_function

    def asm_repr(self):                 ## AsmVar asm_var, str() expands to VM variable name ("vN")
        return self.asm_var

class VmParameterSymbol(VariableSymbol):
    def __init__(self, ctype, cname, asm_par):
        super().__init__(ctype, cname)
        self.asm_par = asm_par

    def asm_repr(self):                 ## str asm_par, VM parameter name ("pN")
        return self.asm_par

class FunctionSymbol(AbstractSymbol):
    def __init__(self, cname, function):
        super().__init__(cname)
        self.function = function

class UserDefFunctionSymbol(FunctionSymbol):
    def asm_repr(self):                 ## AsmTag asm_tag, str() expands to function entry point's TAG
        return self.function.asm_tag

class VmApiFunctionSymbol(FunctionSymbol):
    def asm_repr(self):                 ## str vm_func_instr, VM function's assembly language instruction
        return self.function.vm_func_instr

## ---------------------------------------------------------------------------

class EmulatedInstrs:
    EMULATED_INSTR = {
        'NEG':  'int NEG(): A=-A; F=A',
        'NOT':  'int NOT(): A=~A; F=A',
        'NOTL': 'int NOTL(): A=!A; A:(0|1)',
        'ANDL': f'int ANDL({SCR0}): A=(A && {SCR0}); A:(0|1)',
        'ORL':  f'int ORL({SCR0}): A=(A || {SCR0}); A:(0|1)',
        'EQ':   f'int EQ({SCR0}): A=(A == {SCR0}); A:(0|1)',
        'NE':   f'int NE({SCR0}): A=(A != {SCR0}); A:(0|1)',
        'GT':   f'int GT({SCR0}): A=(A > {SCR0}); A:(0|1)',
        'GE':   f'int GE({SCR0}): A=(A >= {SCR0}); A:(0|1)',
        'LT':   f'int LT({SCR0}): A=(A < {SCR0}); A:(0|1)',
        'LE':   f'int LE({SCR0}): A=(A <= {SCR0}); A:(0|1)' }

    INLINED_INSTR = ('NEG', 'NOT')

    class InstrFunc:
        def __init__(self, instr, asm_tag, asm_buf):
            self.instr = instr          ## str, emulated instruction name
            self.asm_tag = asm_tag      ## AsmTag, emulator function entry point's TAG
            self.asm_buf = asm_buf      ## AsmBuffer, emulator function body's statement buffer

    def __init__(self):
        self.instr_funcs = {}           ## dict(str instr: InstrFunc instr_func), emulated instructions

    def is_emulated(self, instr):
        return instr in self.EMULATED_INSTR

    def asm_bufs(self):
        return [instr_func.asm_buf for instr_func in self.instr_funcs.values()]

    def compile_instr(self, instr, asm_out): ## A := instr(A); F := undef
        if instr in self.instr_funcs:
            asm_out('CALL', self.instr_funcs[instr].asm_tag, comment=instr)
        elif instr in self.INLINED_INSTR:
            getattr(self, f'_compile_{instr}_inline')(asm_out)
        else:
            instr_asm_tag = AsmTag()
            instr_asm_out = AsmBuffer()
            instr_asm_out('TAG', instr_asm_tag, comment=self.EMULATED_INSTR[instr])
            getattr(self, f'_compile_{instr}_definition')(instr_asm_out)
            instr_asm_out('RET')
            self.instr_funcs[instr] = self.InstrFunc(instr, instr_asm_tag, instr_asm_out)
            asm_out('CALL', instr_asm_tag, comment=instr)

    def _compile_NEG_inline(self, asm_out):
        asm_out('XOR', '0xffffffff')    ## A := A ^ 0xffffffff
        asm_out('ADD', 1)               ## A := A + 1; F := A

    def _compile_NOT_inline(self, asm_out):
        asm_out('XOR', '0xffffffff')    ## A := A ^ 0xffffffff; F := A

    def _compile_NOTL_definition(self, asm_out):
        true_tag = AsmTag()
        asm_out('OR', 0, comment='F=A') ## assert F := A before conditional jump
        asm_out('JZ', true_tag)         ## IF (F == 0) GOTO true_tag
        asm_out('LDA', 0)
        asm_out('RET')                  ## return FALSE
        asm_out('TAG', true_tag)        ## true_tag: return TRUE
        asm_out('LDA', 1)

    def _compile_ANDL_definition(self, asm_out):
        ret_tag = AsmTag()
        asm_out('OR', 0, comment='F=A') ## assert F := A before conditional jump
        asm_out('JZ', ret_tag)          ## IF (F == 0) GOTO ret_tag
        asm_out('LDA', SCR0)
        asm_out('OR', 0, comment='F=A') ## assert F := A before conditional jump
        asm_out('JZ', ret_tag)          ## IF (F == 0) GOTO ret_tag
        asm_out('LDA', 1)
        asm_out('TAG', ret_tag)         ## ret_tag: return TRUE or FALSE

    def _compile_ORL_definition(self, asm_out):
        true_tag = AsmTag()
        asm_out('OR', SCR0)             ## A := A | SCR0, F := A
        asm_out('JNZ', true_tag)        ## IF (F != 0) GOTO true_tag
        asm_out('RET')                  ## return FALSE
        asm_out('TAG', true_tag)        ## true_tag: return TRUE
        asm_out('LDA', 1)

    def _compile_EQ_definition(self, asm_out):
        true_tag = AsmTag()
        asm_out('CMP', SCR0)            ## F := A - SCR0
        asm_out('JZ', true_tag)         ## IF (F == 0) GOTO true_tag
        asm_out('LDA', 0)
        asm_out('RET')                  ## return FALSE
        asm_out('TAG', true_tag)        ## true_tag: return TRUE
        asm_out('LDA', 1)

    def _compile_NE_definition(self, asm_out):
        true_tag = AsmTag()
        asm_out('CMP', SCR0)            ## F := A - SCR0
        asm_out('JNZ', true_tag)        ## IF (F != 0) GOTO true_tag
        asm_out('LDA', 0)               ## A := 0
        asm_out('RET')                  ## return FALSE
        asm_out('TAG', true_tag)        ## true_tag: return TRUE
        asm_out('LDA', 1)

    def _compile_GT_definition(self, asm_out):
        false_tag = AsmTag()
        asm_out('CMP', SCR0)            ## F := A - SCR0
        asm_out('JZ', false_tag)        ## IF (F == 0) GOTO false_tag
        asm_out('JM', false_tag)        ## IF (F < 0) GOTO false_tag
        asm_out('LDA', 1)
        asm_out('RET')                  ## return TRUE
        asm_out('TAG', false_tag)       ## false_tag: return FALSE
        asm_out('LDA', 0)

    def _compile_GE_definition(self, asm_out):
        true_tag = AsmTag()
        asm_out('CMP', SCR0)            ## F := A - SCR0
        asm_out('JP',  true_tag)        ## IF (F >= 0) GOTO true_tag
        asm_out('LDA', 0)
        asm_out('RET')                  ## return FALSE
        asm_out('TAG', true_tag)        ## true_tag: return TRUE
        asm_out('LDA', 1)

    def _compile_LT_definition(self, asm_out):
        true_tag = AsmTag()
        asm_out('CMP', SCR0)            ## F := A - SCR0
        asm_out('JM',  true_tag)        ## IF (F < 0) GOTO true_tag
        asm_out('LDA', 0)
        asm_out('RET')                  ## return FALSE
        asm_out('TAG', true_tag)        ## true_tag: return TRUE
        asm_out('LDA', 1)

    def _compile_LE_definition(self, asm_out):
        true_tag = AsmTag()
        asm_out('CMP', SCR0)            ## F := A - SCR0
        asm_out('JZ', true_tag)         ## IF (F == 0) GOTO true_tag
        asm_out('JM', true_tag)         ## IF (F < 0) GOTO true_tag
        asm_out('LDA', 0)
        asm_out('RET')                  ## return FALSE
        asm_out('TAG', true_tag)        ## true_tag: return TRUE
        asm_out('LDA', 1)

## ---------------------------------------------------------------------------

class Pcc:
    UNARY_OP_INSTR = {                      ## 3 arithmetic + 1 logical ops
        '+':  None,                         ## A=+A; F=undef/A (CIS/EIS)
        '-':  'NEG',                        ## A=-A; F=undef/A (CIS/EIS)
        '~':  'NOT',                        ## A=~A; F=undef/A (CIS/EIS)
        '!':  'NOTL' }                      ## A=!A; F=undef/A (CIS/EIS); A:(0|1)

    BINARY_OP_INSTR = {                     ## 10 arithmetic + 2 logical + 6 comparison ops
        '+':  'ADD',                        ## A+=x; F=A
        '-':  'SUB',                        ## A-=x; F=A
        '*':  'MLT',                        ## A*=x; F=A
        '/':  'DIV',                        ## A/=x; F=A
        '%':  'MOD',                        ## A%=x; F=A
        '&':  'AND',                        ## A&=x; F=A
        '|':  'OR',                         ## A|=x; F=A
        '^':  'XOR',                        ## A^=x; F=A
        '<<': 'RLA',                        ## A<<=x; F=A
        '>>': 'RRA',                        ## A>>=x; F=A
        '&&': 'ANDL',                       ## A=(A && x); F=undef/A (CIS/EIS); A:(0|1)
        '||': 'ORL',                        ## A=(A || x); F=undef/A (CIS/EIS); A:(0|1)
        '==': 'EQ',                         ## A=(A == x); F=undef/A (CIS/EIS); A:(0|1)
        '!=': 'NE',                         ## A=(A != x); F=undef/A (CIS/EIS); A:(0|1)
        '>':  'GT',                         ## A=(A >  x); F=undef/A (CIS/EIS); A:(0|1)
        '>=': 'GE',                         ## A=(A >= x); F=undef/A (CIS/EIS); A:(0|1)
        '<':  'LT',                         ## A=(A <  x); F=undef/A (CIS/EIS); A:(0|1)
        '<=': 'LE' }                        ## A=(A <= x); F=undef/A (CIS/EIS); A:(0|1)

    def __init__(self, c_sources, debug):
        self.c_sources = c_sources          ## CSourceBundle, C sources to compile
        self.debug = debug                  ## bool, True: show extra debug output
        self.error_count = 0                ## int, error counter
        self.var_count = None               ## int, number of VM variables allocated
        self.tag_count = None               ## int, number of VM tags allocated
        self.asm_buf = AsmBuffer()          ## AsmBuffer, root output buffer
        self.asm_out = self.asm_buf         ## AsmBuffer, current output buffer
        self.scope = collections.ChainMap() ## ChainMap, current scope with chained parents
        self.functions = {}                 ## dict(str func_name: Function function), user-defined and VM API functions
        self.in_expression = False          ## bool, True: currently evaluating an expression
        self.context_function = None        ## None or UserDefFunction, current function context
        self.loop_tag_stack = []            ## list(), stack of loop AsmTag contexts
        self.loop_continue_tag = None       ## None or AsmTag, current tag to JMP to in case of a "continue" statement
        self.loop_break_tag = None          ## None or AsmTag, current tag to JMP to in case of a "break" statement
        self.all_asm_bufs = None            ## list(AsmBuf asm_buf, ...), list of all buffers
        self.all_asm_vars = None            ## list(AsmVar asm_var, ...), list of all variables
        self.em_instrs = EmulatedInstrs()   ## EmulatedInstrs, set of emulated instructions used

    def compile(self, root_node, do_reduce=True):
        main_function, userdef_functions = self.compile_1st_stage(root_node)
        if self.error_count == 0:
            all_asm_bufs = self.compile_2nd_stage(main_function, userdef_functions, do_reduce)
            self.compile_3rd_stage(all_asm_bufs)
        return self.error_count

    def encode_asm(self, use_comments=False, file=None):
        asm_lines = []
        if use_comments:
            asm_lines.append('; VM variables:')
            asm_lines.append(';')
            asm_lines.append(';  v0: reserved: SCR0')
            asm_lines.append(';  v1: reserved: ARG0')
            asm_lines.append(';  v2: reserved: ARG1')
            asm_lines.append(';  v3: reserved: ARG2')
            for asm_var in self.all_asm_vars:
                asm_lines.append(asm_var.format_decl_comment(self.c_sources))
        for i_buf, asm_buf in enumerate(self.all_asm_bufs):
            if len(asm_lines) > 0:
                asm_lines.append('')
            asm_lines.extend(asm_buf.format_statements(use_comments))
        result = '\n'.join(asm_lines)
        if file is not None:
            print(result, file=file)
        return result

    ## Private functions

    def log_error(self, e, context_function=None):
        self._log_message(e.node, f'error: {e}', context_function)
        if e.node is not None and self.debug:
            print('Extra debug node information:\n' + str(e.node), file=sys.stderr)
        self.error_count += 1

    def log_warning(self, node, message, context_function):
        self._log_message(node, f'warning: {message}', context_function)

    def _log_message(self, node, message, context_function):
        if node is None:
            print(message, file=sys.stderr)
        else:
            flat_row, col = node.coord.line, node.coord.column
            func_name = context_function.func_name if context_function is not None else None
            print(self.c_sources.format_src_message(flat_row, col, message, ctx_func_name=func_name), file=sys.stderr)

    def push_scope(self):
        self.scope = self.scope.new_child()

    def pop_scope(self):
        self.scope = self.scope.parents

    def push_loop_tags(self, begin_tag, end_tag):
        self.loop_tag_stack.append((self.loop_continue_tag, self.loop_break_tag))
        self.loop_continue_tag = begin_tag
        self.loop_break_tag = end_tag

    def pop_loop_tags(self):
        self.loop_continue_tag, self.loop_break_tag = self.loop_tag_stack.pop()

    def find_symbol(self, cname, filter=None):
        symbol = self.scope.get(cname, None)
        if symbol is not None and (filter is None or isinstance(symbol, filter)):
            return symbol
        return None

    def bind_symbol(self, node, sym_obj):
        if sym_obj.cname in self.scope.maps[0]:
            raise PccError(node, f'redefinition of "{sym_obj.cname}"')
        self.scope.maps[0][sym_obj.cname] = sym_obj
        return sym_obj

    def declare_enum(self, enum_decl):
        enum_cursor = 0
        for enum_node in enum_decl.values.enumerators:
            value_node = enum_node.value
            if value_node is None:
                enum_value = str(enum_cursor)
                enum_cursor += 1
            else:
                const_value = self.try_parse_constant(value_node)
                if const_value is None:
                    raise PccError(value_node, 'unsupported enum syntax')
                enum_value = const_value
                enum_cursor = int(enum_value, 0) + 1
            self.bind_symbol(enum_node, EnumSymbol(enum_node.name, enum_value))

    def declare_variable(self, node, ctype, cname, asm_var=None):
        return self.bind_symbol(node, VmVariableSymbol(ctype, cname, asm_var, node, self.context_function))

    def declare_parameter(self, node, ctype, cname):
        m = re.fullmatch('(?:.*_)?(p[0-9])(?:_.*)?', cname)
        if not m:
            raise PccError(node, 'external variable names must contain one of "p0", "p1", ..., "p9"')
        vm_param_name = m.groups(0)[0]
        return self.bind_symbol(node, VmParameterSymbol(ctype, cname, vm_param_name))

    def declare_function(self, node, is_vm_function=False):
        ## find or create global Function object
        if is_vm_function:
            function = VmApiFunction(node)
        else:
            function = UserDefFunction(node)
        func_name = node.name
        if func_name not in self.functions:
            self.functions[func_name] = function
        else:
            if not function.matches(self.functions[func_name]):
                raise PccError(node, 'function prototype conflicts with previous declaration')
            function = self.functions[func_name]
        ## return previously declared function symbol or bind new symbol to current scope
        func_sym = self.find_symbol(func_name, filter=FunctionSymbol)
        if func_sym is not None:
            return func_sym
        elif is_vm_function:
            func_sym = VmApiFunctionSymbol(func_name, function)
        else:
            func_sym = UserDefFunctionSymbol(func_name, function)
        return self.bind_symbol(node, func_sym)

    def try_parse_constant(self, node):
        result = None
        if isinstance(node, c_ast.Constant) and node.type == 'int':
            result = node.value
        elif isinstance(node, c_ast.ID):
            enum_sym = self.find_symbol(node.name, filter=EnumSymbol)
            if enum_sym is not None:
                result = enum_sym.const_value
        elif isinstance(node, c_ast.UnaryOp) and node.op == '-':
            if isinstance(node.expr, c_ast.Constant):
                result = str(-int(node.expr.value, 0))
            elif isinstance(node.expr, c_ast.ID):
                enum_sym = self.find_symbol(node.expr.name, filter=EnumSymbol)
                if enum_sym is not None:
                    result = str(-int(enum_sym.const_value, 0))
        return result

    def try_parse_term(self, node):
        result = self.try_parse_constant(node)
        if result is None and isinstance(node, c_ast.ID):
            var_sym = self.find_symbol(node.name, filter=VariableSymbol)
            if var_sym is None:
                raise PccError(node, f'undeclared variable "{node.name}"')
            result = var_sym.asm_repr()
        return result

    ## Code-generating functions

    def compile_1st_stage(self, root_node):
        ## compile top-level declarations and user-defined functions
        for node in root_node:
            try:
                if isinstance(node, (c_ast.Decl, c_ast.FuncDef)):
                    self.compile_statement(node)
                else:
                    raise PccError(node, 'unsupported syntax')
            except PccError as e:
                self.log_error(e)
        ## collect user-defined functions and main function
        userdef_functions = []
        main_function = None
        for func_name, function in self.functions.items():
            if isinstance(function, UserDefFunction):
                if func_name == 'main':
                    main_function = function
                else:
                    userdef_functions.append(function)
        ## incrementally drop non-called function hierarchies
        while len(userdef_functions) > 0:
            functions_passed = []
            func_names_dropped = set()
            for function in userdef_functions:
                if len(function.caller) > 0:
                    functions_passed.append(function)
                else:
                    func_names_dropped.add(function.func_name)
            if len(func_names_dropped) == 0:
                break
            for function in functions_passed:
                function.caller -= func_names_dropped
            userdef_functions = functions_passed
        ## check user-defined functions and main function
        for function in userdef_functions:
            if function.impl_node is None:
                self.log_error(PccError(function.decl_node,
                    f'missing "{function.func_name}()" function implementation'))
        if main_function is None or main_function.impl_node is None:
            self.log_error(PccError(None, 'missing "main()" function implementation'))
        return main_function, userdef_functions

    def compile_2nd_stage(self, main_function, userdef_functions, do_reduce):
        ## drop unused tags in user-defined functions
        tags = {}   ## dict(AsmTag asm_tag: int use_count), preseed w. user-defined functions
        for function in userdef_functions:
            tags[function.asm_tag] = 1
        userdef_asm_bufs = [main_function.asm_buf] + [f.asm_buf for f in userdef_functions]
        for asm_buf in userdef_asm_bufs:
            asm_buf.drop_unused_tags(tags.copy())
            if do_reduce:
                asm_buf.reduce()
        ## merge main() function body into init segment
        main_function.asm_buf.replace_instruction('RET', 'HALT')
        self.asm_buf.extend(main_function.asm_buf)
        return [self.asm_buf] + userdef_asm_bufs[1:] + self.em_instrs.asm_bufs()

    def compile_3rd_stage(self, all_asm_bufs):
        ## bind VM tags
        tag_count = 0
        tag_base = 0
        for asm_buf in all_asm_bufs:
            n_tags = asm_buf.bind_tags(tag_base)
            tag_count += n_tags
            tag_base = ((tag_base + n_tags + 10) // 10) * 10
        ## bind VM variables
        global_asm_vars = dict()    ## dict(AsmVar asm_var: any)
        local_asm_vars = dict()     ## dict(AsmVar asm_var: any)
        for asm_buf in all_asm_bufs:
            asm_buf.collect_vm_variables(global_asm_vars, local_asm_vars)
        all_asm_vars = list(global_asm_vars.keys()) + list(local_asm_vars.keys())
        var_count = 1 + len(ARG_REGS)
        for asm_var in all_asm_vars:
            asm_var.bind(var_count)
            var_count += 1
        self.tag_count = tag_count
        self.var_count = var_count
        self.all_asm_bufs = all_asm_bufs
        self.all_asm_vars = all_asm_vars

    def compile_expression(self, node):                 ## A := (node-expr), F := undef/A (CIS/EIS)
        node_term = self.try_parse_term(node)
        if node_term is not None:
            self.asm_out('LDA', node_term)
        elif isinstance(node, (c_ast.UnaryOp, c_ast.BinaryOp, c_ast.Assignment, c_ast.FuncCall)):
            prev_in_expression = self.in_expression
            self.in_expression = True
            try:
                self.compile_statement(node)
            finally:
                self.in_expression = prev_in_expression
        else:
            raise PccError(node, 'unsupported expression syntax')

    def compile_assignment(self, dst_reg, rhs_node, assign_op='='):
        rhs_term = self.try_parse_term(rhs_node)
        if assign_op == '=':                            ## Simple assignment ("=")
            if rhs_term is not None:
                self.asm_out('LD', dst_reg, rhs_term)   ## dst_reg := (rhs-term)
                if self.in_expression:
                    self.asm_out('LDA', dst_reg)        ## A := dst_reg; F := undef/A (CIS/EIS)
            else:
                self.compile_expression(rhs_node)       ## A := (rhs-expr); F := undef/A (CIS/EIS)
                self.asm_out('STA', dst_reg)            ## dst_reg := A
        elif assign_op[:-1] in self.BINARY_OP_INSTR:    ## Assignment operator ("+=", "/=", ...)
            op_instr = self.BINARY_OP_INSTR[assign_op[:-1]]
            if rhs_term is not None:
                self.asm_out('LDA', dst_reg)            ## A := dest_reg
                self.asm_out(op_instr, rhs_term)        ## A := A <OP> (rhs-term); F := A
            else:
                self.compile_expression(rhs_node)       ## A := (rhs-expr); F := undef/A (CIS/EIS)
                self.asm_out('STA', SCR0)               ## SCR0 := A
                self.asm_out('LDA', dst_reg)            ## A := dest_reg
                self.asm_out(op_instr, SCR0)            ## A := A <OP> SCR0; F := A
            self.asm_out('STA', dst_reg)                ## dst_reg := A
        else:
            raise PccError(rhs_node, f'unsupported assignment operator "{assign_op}"')

    def compile_asm_statement(self, node):
        if node.args is None or not isinstance(node.args, c_ast.ExprList) or len(node.args.exprs) == 0:
            return False
        ## parse arguments into instr_args[]
        instr_args = []
        is_1st_arg_str = False
        for i_arg, arg_expr in enumerate(node.args.exprs):
            arg_term = self.try_parse_term(arg_expr)
            if arg_term is None and isinstance(arg_expr, c_ast.Constant) and arg_expr.type == 'string':
                arg_term = bytes(arg_expr.value[1:-1], 'utf-8').decode('unicode_escape')
                if i_arg == 0:
                    is_1st_arg_str = True
            if arg_term is None:
                raise PccError(arg_expr, 'asm() expects arguments to be variables, int or string constants')
            instr_args.append(arg_term)
        if not is_1st_arg_str:
            raise PccError(node.args.exprs[0], 'asm() expects first argument to be a string constant')
        instr = instr_args.pop(0).upper()
        ## replace user-defined static TAG labels with AsmTag objects
        if AsmCmd.tag_instr_idx(instr) >= 0:
            if len(instr_args) != 1:
                raise PccError(node, f'{instr} expects a single tag label argument')
            tag_label = instr_args[0]
            static_tag = self.context_function.static_asm_tags.get(tag_label, None)
            if static_tag is None:
                static_tag = AsmTag()
                self.context_function.static_asm_tags[tag_label] = static_tag
            instr_args[0] = static_tag
        ## append raw assembler statement to current buffer
        self.asm_out(instr, *instr_args)
        return instr in ('RET', 'HALT')

    def compile_statement(self, node):
        ast_class_name = node.__class__.__name__
        _compile_class_node = getattr(self, f'_compile_{ast_class_name}_node', None)
        if not callable(_compile_class_node):
            raise PccError(node, f'unsupported statement syntax (AST element {ast_class_name})')
        return _compile_class_node(node)

    def _compile_UnaryOp_node(self, node):
        if node.op in ('++', '--', 'p++', 'p--'):
            if not isinstance(node.expr, c_ast.ID):
                raise PccError(node, 'increment operator expects variable')
            reg_sym = self.find_symbol(node.expr.name, filter=VariableSymbol)
            if reg_sym is None:
                raise PccError(node.expr, f'undefined variable "{node.expr.name}"')
            vm_reg = reg_sym.asm_repr()
            if node.op == '++':                     ## Prefix increment "++X":
                self.asm_out('INR', vm_reg)         ## ++X, F := X
                self.asm_out('LDA', vm_reg)         ## A := X, F := A
            elif node.op == '--':                   ## Prefix deccrement "--X":
                self.asm_out('DCR', vm_reg)         ## --X, F := X
                self.asm_out('LDA', vm_reg)         ## A := X, F := A
            elif node.op == 'p++':                  ## Postfix increment "X++":
                self.asm_out('LD', SCR0, vm_reg)    ## SCR0 := X
                self.asm_out('INR', vm_reg)         ## ++X, F := X
                self.asm_out('LDA', SCR0)           ## A := SCR0, F := undef/A (CIS/EIS)
            elif node.op == 'p--':                  ## Postfix decrement "X--":
                self.asm_out('LD', SCR0, vm_reg)    ## SCR0 := X
                self.asm_out('DCR', vm_reg)         ## --X, F := X
                self.asm_out('LDA', SCR0)           ## A := SCR0; F := undef/A (CIS/EIS)
        elif node.op in self.UNARY_OP_INSTR:
            self.compile_expression(node.expr)      ## A := (expr); F := undef/A (CIS/EIS)
            op_instr = self.UNARY_OP_INSTR[node.op]
            if op_instr is not None:
                self.em_instrs.compile_instr(op_instr, self.asm_out) ## A := <OP> A; F := undef
        else:
            raise PccError(node, f'unsupported unary operator "{node.op}"')
        return False

    def _compile_BinaryOp_node(self, node):
        if node.op not in self.BINARY_OP_INSTR:
            raise PccError(node, f'unsupported binary operator "{node.op}"')
        op_instr = self.BINARY_OP_INSTR[node.op]
        ## compile left-hand side (lhs) into ACC
        self.compile_expression(node.left)          ## A := (lhs-expr); F := undef/A (CIS/EIS)
        ## compile right-hand side (rhs) and combine with lhs using <OP>
        rhs_term = self.try_parse_term(node.right)
        if rhs_term is not None:
            if self.em_instrs.is_emulated(op_instr):
                self.asm_out('LD', SCR0, rhs_term)
                self.em_instrs.compile_instr(op_instr, self.asm_out) ## A := A <OP> A; F := undef
            else:
                self.asm_out(op_instr, rhs_term)    ## A := A <OP> x, F := A
        else:
            self.asm_out('PUSHA')                   ## save ACC (lhs) onto stack
            self.compile_expression(node.right)     ## A := (rhs-expr); F := undef/A (CIS/EIS)
            self.asm_out('STA', SCR0)               ## SCR0 := A
            self.asm_out('POPA')                    ## restore lhs in ACC from stack
            if self.em_instrs.is_emulated(op_instr):
                self.em_instrs.compile_instr(op_instr, self.asm_out) ## A := A <OP> A; F := undef
            else:
                self.asm_out(op_instr, SCR0)        ## A := A <OP> SCR0, F := A
        return False

    def _compile_Assignment_node(self, node):
        lhs_sym = self.find_symbol(node.lvalue.name, filter=VariableSymbol)
        if lhs_sym is None:
            raise PccError(node.lvalue, f'undefined variable "{node.lvalue.name}"')
        lhs_reg = lhs_sym.asm_repr()
        self.compile_assignment(lhs_reg, node.rvalue, assign_op=node.op)
        return False

    def _compile_Compound_node(self, node):
        returned = False
        if node.block_items is not None:
            self.push_scope()
            try:
                in_unreachable_code = False
                for statement_node in node.block_items:
                    if in_unreachable_code:
                        self.log_warning(statement_node, 'unreachable code', self.context_function)
                        break
                    try:
                        s_returned = self.compile_statement(statement_node)
                        if s_returned:
                            returned = True
                        if s_returned or isinstance(statement_node, (c_ast.Continue, c_ast.Break)):
                            in_unreachable_code = True
                    except PccError as e:
                        self.log_error(e, context_function=self.context_function)
            finally:
                self.pop_scope()
        return returned

    def _compile_Return_node(self, node):
        ret_val_expected = self.context_function.has_return
        ret_val_given = node.expr is not None
        if not ret_val_expected and ret_val_given:
            self.log_warning(node, 'function does not return a value', self.context_function)
        elif ret_val_expected and not ret_val_given:
            self.log_warning(node, 'function should return a value', self.context_function)
        elif ret_val_given:
            self.compile_expression(node.expr)              ## A := (expr); F := A
        self.asm_out('RET')
        return True

    def _compile_Decl_node(self, node):
        if len(node.align) != 0 or node.bitsize is not None or len(node.funcspec) != 0:
            raise PccError(node, 'unsupported declaration syntax')
        is_extern = False
        if len(node.storage) > 0:
            if len(node.storage) != 1 or node.storage[0] != 'extern':
                raise PccError(node, f'unsupported storage qualifier "{" ".join(node.storage)}"')
            is_extern = True
        decl_type = node.type
        if isinstance(decl_type, c_ast.TypeDecl):
            if len(decl_type.quals) != 0:
                raise PccError(node, f'unsupported type qualifier "{" ".join(decl_type.quals)}"')
            if isinstance(decl_type.type, c_ast.IdentifierType):
                if len(decl_type.type.names) == 1 and decl_type.type.names[0] in ('int', 'long'):
                    var_ctype = decl_type.type.names[0]
                else:
                    raise PccError(node, f'unsupported variable type "{" ".join(decl_type.type.names)}"')
            elif isinstance(decl_type.type, c_ast.Enum):
                self.declare_enum(decl_type.type)
                var_ctype = 'int'
            else:
                raise PccError(decl_type, 'unsupported variable type')
            var_cname = decl_type.declname
            if is_extern:
                var_sym = self.declare_parameter(node, var_ctype, var_cname)
            else:
                var_sym = self.declare_variable(node, var_ctype, var_cname)
            if node.init is not None:
                self.compile_assignment(var_sym.asm_repr(), node.init)
        elif isinstance(decl_type, c_ast.FuncDecl):
            self.declare_function(node, is_vm_function=is_extern)
        elif isinstance(decl_type, c_ast.Enum):
            self.declare_enum(decl_type)
        else:
            raise PccError(node, 'unsupported declaration syntax')
        return False

    def _compile_FuncDef_node(self, node):
        func_sym = self.declare_function(node.decl)     ## UserDefFunctionSymbol func_sym
        function = func_sym.function
        if function.impl_node is not None:
            raise PccError(node, f'redefinition of "{function.func_name}"')
        function.impl_node = node
        ## enter function context
        self.context_function = function
        self.asm_out = function.asm_buf
        self.push_scope()
        try:
            if function.func_name != 'main':
                self.asm_out('TAG', function.asm_tag, comment=function.decl_str())
            if function.arg_count > 0:
                arg_vars = function.arg_vars
                arg_ctypes = function.arg_ctypes
                for i_arg, arg_param in enumerate(node.decl.type.args.params):
                    arg_ctype = arg_ctypes[i_arg]
                    arg_cname = arg_param.name
                    if arg_cname is None:
                        arg_cname = f'.{function.func_name}.{i_arg}'
                    self.declare_variable(node.body, arg_ctype, arg_cname, asm_var=arg_vars[i_arg])
            returned = self._compile_Compound_node(node.body)
            if not returned:
                if function.has_return:
                    self.log_warning(node, 'function should return a value', function)
                self.asm_out('RET')
        except PccError as e:
            self.log_error(e, context_function=function)
        finally:
            self.pop_scope()
            self.asm_out = self.asm_buf
            self.context_function = None
        return False

    def _compile_FuncCall_node(self, node):
        func_name = node.name.name
        if func_name == 'asm':
            return self.compile_asm_statement(node)
        returned = False
        func_sym = self.find_symbol(func_name, filter=FunctionSymbol)
        if func_sym is None:
            raise PccError(node, f'undeclared function "{func_name}"')
        function = func_sym.function
        if self.in_expression and not function.has_return:
            raise PccError(node, 'function declared without return value')
        arg_count = len(node.args.exprs) if node.args is not None else 0
        if function.arg_count != arg_count:
            raise PccError(node, f'function expects {function.arg_count} argument(s) instead of {arg_count}')
        if isinstance(func_sym, VmApiFunctionSymbol):
            ## compile call to VM API function
            args = []
            for i_arg in range(function.arg_count):
                arg_expr_node = node.args.exprs[i_arg]
                arg_term = function.map_argument(arg_expr_node, i_arg, self.try_parse_constant(arg_expr_node))
                if arg_term is None:
                    arg_term = self.try_parse_term(arg_expr_node)
                if arg_term is None:
                    arg_term = ARG_REGS[i_arg]
                    self.compile_assignment(arg_term, arg_expr_node)
                args.append(arg_term)
            asm_instr = func_sym.asm_repr()
            if asm_instr == 'HALT':
                returned = True
            self.asm_out(asm_instr, *args, comment=f'{func_name}();')               ## A := vm_api_func(); F := A
        else:
            ## compile call to user defined function
            if function is not self.context_function:
                function.caller.add(self.context_function.func_name)
            for i_arg in range(function.arg_count):
                arg_expr_node = node.args.exprs[i_arg]
                arg_asm_var = function.arg_vars[i_arg]
                self.compile_assignment(arg_asm_var, arg_expr_node)
            self.asm_out('CALL', func_sym.asm_repr(), comment=f'{func_name}();')    ## A := user_func(); F := undef/A (CIS/EIS)
        return returned

    def _compile_If_node(self, node):
        else_tag = AsmTag() if node.iffalse is not None else None
        endif_tag = AsmTag()
        self.compile_expression(node.cond)                  ## A := (cond); F := undef/A (CIS/EIS)
        self.asm_out('OR', 0, comment='F=A')                ## assert F := A before conditional jump
        if else_tag is None:
            self.asm_out('JZ', endif_tag)                   ## NOT A AND no-else-branch: GOTO endif_tag
        else:
            self.asm_out('JZ', else_tag)                    ## NOT A AND has-else-branch: GOTO else_tag
        r1 = self.compile_statement(node.iftrue)            ## compile if-branch statement(s)
        r2 = False
        if else_tag is not None:
            if not r1:                                      ## omit the following JMP when if-branch returned (RET)
                self.asm_out('JMP', endif_tag)              ## has-else-branch: GOTO endif_tag
            self.asm_out('TAG', else_tag)                   ## TAG: else_tag
            r2 = self.compile_statement(node.iffalse)       ## compile else-branch
        self.asm_out('TAG', endif_tag)                      ## TAG: endif_tag
        return r1 and r2

    def _compile_While_node(self, node):
        begin_tag = AsmTag()
        end_tag = AsmTag()
        self.push_loop_tags(begin_tag, end_tag)
        try:
            self.asm_out('TAG', begin_tag)                  ## TAG: begin_tag
            self.compile_expression(node.cond)              ## A := (cond); F := undef/A (CIS/EIS)
            self.asm_out('OR', 0, comment='F=A')            ## assert F := A before conditional jump
            self.asm_out('JZ', end_tag)                     ## cond == FALSE: GOTO end_tag
            returned = self.compile_statement(node.stmt)    ## compile statement(s)
            self.asm_out('JMP', begin_tag)                  ## GOTO begin_tag
            self.asm_out('TAG', end_tag)                    ## TAG: end_tag
        finally:
            self.pop_loop_tags()
        return returned

    def _compile_DoWhile_node(self, node):
        begin_tag = AsmTag()
        end_tag = AsmTag()
        self.push_loop_tags(begin_tag, end_tag)
        try:
            self.asm_out('TAG', begin_tag)                  ## TAG: begin_tag
            returned = self.compile_statement(node.stmt)    ## compile statement(s)
            self.compile_expression(node.cond)              ## A := (cond); F := undef/A (CIS/EIS)
            self.asm_out('OR', 0, comment='F=A')            ## assert F := A before conditional jump
            self.asm_out('JNZ', begin_tag)                  ## cond == TRUE: GOTO begin_tag
            self.asm_out('TAG', end_tag)                    ## TAG: end_tag
        finally:
            self.pop_loop_tags()
        return returned

    def _compile_For_node(self, node):
        begin_tag = AsmTag()
        next_tag = AsmTag()
        end_tag = AsmTag()
        self.push_loop_tags(next_tag, end_tag)
        try:
            needs_local_scope = node.init is not None and isinstance(node.init, c_ast.DeclList)
            if needs_local_scope:
                self.push_scope()
            try:
                if node.init is not None:                       ## compile init-clause statement(s)
                    if isinstance(node.init, c_ast.DeclList):
                        for decl_node in node.init.decls:
                            self._compile_Decl_node(decl_node)
                    else:
                        self.compile_statement(node.init)
                self.asm_out('TAG', begin_tag)                  ## TAG: begin_tag
                if node.cond is not None:
                    self.compile_expression(node.cond)          ## A := (cond); F := undef/A (CIS/EIS)
                    self.asm_out('OR', 0, comment='F=A')        ## assert F := A before conditional jump
                    self.asm_out('JZ', end_tag)                 ## cond == FALSE: GOTO end_tag
                returned = self.compile_statement(node.stmt)    ## compile loop-body statement(s)
                self.asm_out('TAG', next_tag)                   ## TAG: next_tag
                if node.next is not None:                       ## compile iteration-expression(s)
                    if isinstance(node.next, c_ast.ExprList):
                        for expr_node in node.next.exprs:
                            self.compile_expression(expr_node)  ## A := (next-expr); F := undef/A (CIS/EIS)
                    else:
                        self.compile_expression(node.next)      ## A := (next-expr); F := undef/A (CIS/EIS)
                self.asm_out('JMP', begin_tag)                  ## GOTO begin_tag
                self.asm_out('TAG', end_tag)                    ## TAG: end_tag
            finally:
                if needs_local_scope:
                    self.pop_scope()
        finally:
            self.pop_loop_tags()
        return returned

    def _compile_Continue_node(self, node):
        if self.loop_continue_tag is None:
            raise PccError(node, '"continue" outside loop not allowed')
        self.asm_out('JMP', self.loop_continue_tag)
        return False

    def _compile_Break_node(self, node):
        if self.loop_break_tag is None:
            raise PccError(node, '"break" outside loop not allowed')
        self.asm_out('JMP', self.loop_break_tag)
        return False

    def _compile_EmptyStatement_node(self, node):
        return False

## ---------------------------------------------------------------------------

class CSourceBundle:
    def read_files(self, filenames):
        self.c_source_files = {}    ## dict(str filename: list(str line))
        self.c_segments = []        ## list(tuple(str seg_filename, int flat_idx_start, int flat_idx_end))
        self.e_location = None      ## tuple(), stores the most recent logged error location
        ttl_line_count = 0          ## int, total number of lines
        c_result = ''               ## str, combined and cleaned source code
        try:
            for filename in filenames:
                with open(filename, 'r') as f:
                    c_source_lines = list(line.rstrip('\r\n') for line in f.readlines())
                self.c_source_files[filename] = c_source_lines
                self.c_segments.append((filename, ttl_line_count, ttl_line_count + len(c_source_lines)))
                ttl_line_count += len(c_source_lines)
                c_result += '\n'.join(c_source_lines) + '\n'
        except OSError as e:
            print(str(e), file=sys.stderr)
            return None
        c_result = re.sub(r'//.*', '', c_result)
        c_result = re.sub(r'/\*(.|\n)*?\*/', lambda m: re.sub(r'[^\n]', '', m.group(0)), c_result)
        return c_result

    def map_coord(self, flat_row):
        ## map flat_row to (filename, row)
        flat_idx = flat_row - 1
        for seg_filename, flat_idx_start, flat_idx_end in self.c_segments:
            if flat_idx >= flat_idx_start and flat_idx < flat_idx_end:
                row = flat_row - flat_idx_start
                return seg_filename, row
        return None, flat_row

    def format_src_message(self, flat_row, col, message, ctx_func_name=None):
        filename, row = self.map_coord(flat_row)
        if filename is None:
            return f':{flat_row}:{col}: {message}'
        ## build error message
        err_message = ''
        if ctx_func_name is not None:
            e_location = (filename, ctx_func_name)
            if self.e_location != e_location:
                self.e_location = e_location
                err_message = f'{filename}: In function "{ctx_func_name}":\n'
        src_line = self.c_source_files[filename][row-1]
        pointer_indent = re.sub(r'[^\t ]', ' ', src_line[:col-1])
        err_message += f'{filename}:{row}:{col}: {message}\n{src_line}\n{pointer_indent}^^^'
        return err_message

def pcc(filenames, debug=False, do_reduce=True, vm_api_h='vm_api.h'):
    if vm_api_h not in [PurePath(filename).name for filename in filenames]:
        filenames = [vm_api_h] + filenames
    ## build C translation unit from input files
    c_sources = CSourceBundle()
    c_translation_unit = c_sources.read_files(filenames)
    if c_translation_unit is None:
        return None
    ## build abstract syntax tree (AST) from C translation unit
    try:
        ast = CParser().parse(c_translation_unit)
    except ParseError as e:
        m = re.fullmatch('[^:]*?:(\d+):(\d+):\s*(.*)', str(e))
        if m is None:
            print(e, file=sys.stderr)
        else:
            flat_row, col, message = int(m[1]), int(m[2]), m[3]
            print(c_sources.format_src_message(flat_row, col, message), file=sys.stderr)
        print('*** aborted with parser error', file=sys.stderr)
        return None
    ## translate AST into assembly language
    cc = Pcc(c_sources, debug)
    if cc.compile(ast, do_reduce=do_reduce) != 0:
        print('*** aborted with compiler error(s)', file=sys.stderr)
        return None
    return cc

def main():
    parser = argparse.ArgumentParser(description='pcc - PIGS C compiler')
    parser.add_argument('filenames', metavar='C_FILE', nargs='+', help='filenames to parse')
    parser.add_argument('-o', dest='out_filename', metavar='FILE', help='place the output into FILE ("-" for STDOUT)')
    parser.add_argument('-c', dest='comments', action='store_true', help='add comments to asm output')
    parser.add_argument('-n', dest='no_reduce', action='store_true', help='do not reduce asm output')
    parser.add_argument('-d', dest='debug', action='store_true', help='add debug output to error messages')
    args = parser.parse_args()

    cc = pcc(args.filenames, debug=args.debug, do_reduce=not args.no_reduce)
    if cc is None:
        return -1
    out_filename = args.out_filename
    if out_filename is None:
        out_filename = PurePath(args.filenames[-1]).stem + '.s'
    if out_filename == '-':
        cc.encode_asm(use_comments=args.comments, file=sys.stdout)
    else:
        with open(out_filename, 'w') as f:
            cc.encode_asm(use_comments=args.comments, file=f)
    print(f'\nVM variables used: {cc.var_count}/150, tags: {cc.tag_count}/50.', file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
