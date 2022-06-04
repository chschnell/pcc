#!/bin/python3m
##
## pcc.py
## PIGS C compiler
##

import sys, argparse, re, collections
from pathlib import PurePath, Path

from pycparser import c_ast
from pycparser.c_parser import CParser
from pycparser.plyparser import ParseError

SCR0     = 'v0'               ## General purpose (scratch) register
ARG_REGS = ('v1', 'v2', 'v3') ## Function argument register (ARG0 ... ARG2)

VM_BINARY_ARITHMETIC_OP = {
    '+':  'ADD',    ## A+=x; F=A
    '-':  'SUB',    ## A-=x; F=A
    '*':  'MLT',    ## A*=x; F=A
    '/':  'DIV',    ## A/=x; F=A
    '%':  'MOD',    ## A%=x; F=A
    '&':  'AND',    ## A&=x; F=A
    '|':  'OR',     ## A|=x; F=A
    '^':  'XOR',    ## A^=x; F=A
    '<<': 'RLA',    ## A<<=x; F=A
    '>>': 'RRA',    ## A>>=x; F=A
}

VM_BINARY_LOGICAL_OP = {
    '&&': 'ANDL',   ## A=(A && SCR0); A:(0|1)
    '||': 'ORL',    ## A=(A || SCR0); A:(0|1)
    '==': 'EQ',     ## A=(A == SCR0); A:(0|1)
    '!=': 'NE',     ## A=(A != SCR0); A:(0|1)
    '>':  'GT',     ## A=(A  > SCR0); A:(0|1)
    '>=': 'GE',     ## A=(A >= SCR0); A:(0|1)
    '<':  'LT',     ## A=(A  < SCR0); A:(0|1)
    '<=': 'LE',     ## A=(A <= SCR0); A:(0|1)
}

HELPER_FUNCTION_DESCR = {
    'NEG':  'NEG(): A=-A; F=A',
    'NOTL': 'NOTL(): A=!A; A:(0|1)',
    'ANDL': 'ANDL(): A=(A && SCR0); A:(0|1)',
    'ORL':  'ORL(): A=(A || SCR0); A:(0|1)',
    'EQ':   'EQ(): A=(A == SCR0); A:(0|1)',
    'NE':   'NE(): A=(A != SCR0); A:(0|1)',
    'GT':   'GT(): A=(A > SCR0); A:(0|1)',
    'GE':   'GE(): A=(A >= SCR0); A:(0|1)',
    'LT':   'LT(): A=(A < SCR0); A:(0|1)',
    'LE':   'LE(): A=(A <= SCR0); A:(0|1)',
}

VM_FUNCTION_CMD = {
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
    'exit':                         'HALT',
}

class PccError(Exception):
    def __init__(self, node, message):
        super().__init__(message)
        self.node = node

def format_src_quote(c_source_files, filename, row, col):
    src_line = c_source_files[filename][row-1]
    pointer_indent = re.sub(r'[^\t ]', ' ', src_line[:col-1])
    return '%s\n%s^^^' % (src_line, pointer_indent)

## ---------------------------------------------------------------------------

class AsmVar:
    def __init__(self, var_sym=None):
        self.vm_var_id = None   ## None (unbound) or str "v0" ... "v149"
        self.var_sym = var_sym  ## VmVariableSymbol var_sym, 1:1 relationship

    def bind(self, vm_var_nr):
        self.vm_var_id = 'v%d' % vm_var_nr

    def __str__(self):
        if self.vm_var_id is None:
            raise Exception('internal error: unbound virtual variable!')
        return self.vm_var_id

    def format_decl_comment(self):
        var_sym = self.var_sym
        coord = var_sym.decl_node.coord
        fqname = var_sym.cname
        if var_sym.context_func_sym is not None:
            fqname = '%s.%s' % (var_sym.context_func_sym.cname, fqname)
        return '; %3s: %s:%s:%s: %s %s' % (self, PurePath(coord.file).name,
            coord.line, coord.column, var_sym.ctype, fqname)

class AsmStatement:
    def __init__(self, comment=None):
        self.comment = comment  ## None or str, optional comment

    def format_statement(self, indent):
        raise NotImplementedError()

class AsmTag(AsmStatement):
    def __init__(self):
        super().__init__()
        self.vm_tag_id = None   ## None (unbound) or str "1", "2", ..., any unique positive integer

    def format_statement(self, indent):
        return 'TAG %s' % self

    def bind(self, vm_tag_id):
        self.vm_tag_id = str(vm_tag_id)

    def __str__(self):
        if self.vm_tag_id is None:
            raise Exception('internal error: unbound virtual tag!')
        return self.vm_tag_id

class AsmCmd(AsmStatement):
    def __init__(self, cmd, args, comment):
        super().__init__(comment=comment)
        self.cmd = cmd          ## str, uppercase assembly language command
        self.args = args        ## list(arg), command's arguments of type int, str, AsmVar or AsmTag

    def format_statement(self, indent):
        return '%s%-5s %s' % (indent, self.cmd, ' '.join([str(arg) for arg in self.args]))

class AsmBranchCmd(AsmCmd):
    pass

class AsmBuffer:
    def __init__(self):
        self.stmt_buf = []      ## list(AsmStatement asm_stmt)

    def __call__(self, cmd, *args, comment=None):
        cmd = cmd.upper()
        is_tag_cmd = cmd == 'TAG'
        is_branch_cmd = cmd in ('CALL', 'JMP', 'JNZ', 'JZ', 'JP', 'JM')
        if (is_branch_cmd or is_tag_cmd) and (len(args) != 1 or not isinstance(args[0], AsmTag)):
            raise Exception('internal error: %s expects AsmTag argument, given "%s"' % (cmd, ' '.join(args)))
        if is_tag_cmd:
            asm_stmt = args[0]
            asm_stmt.comment = comment
        elif is_branch_cmd:
            asm_stmt = AsmBranchCmd(cmd, list(args), comment)
        else:
            asm_stmt = AsmCmd(cmd, list(args), comment)
        self.stmt_buf.append(asm_stmt)

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
                if prev_stmt.cmd == 'RET' and curr_stmt.cmd == 'RET':
                    ## "RET + <RET>" => drop "RET", keep "<RET>"
                    continue
                elif prev_stmt.cmd == 'JMP' and curr_stmt.cmd == 'JMP':
                    ## "JMP X + <JMP Y>" => drop "JMP Y", keep "<JMP X>"
                    continue
                elif prev_stmt.cmd == 'STA' and curr_stmt.cmd == 'LDA' and prev_stmt.args[0] == curr_stmt.args[0]:
                    ## "STA X + <LDA X>" => drop "<LDA Y>", keep "STA X"
                    continue
            elif isinstance(prev_stmt, AsmTag) and isinstance(curr_stmt, AsmTag):
                ## "TAG X + <TAG Y>" => replace all uses of "Y" with "X", keep "TAG X", drop "TAG Y"
                self._replace_tag(curr_stmt, prev_stmt)
                continue
            elif isinstance(prev_stmt, AsmTag) and isinstance(curr_stmt, AsmCmd) and curr_stmt.cmd == 'JMP':
                if len(out_buf) > 2 and isinstance(out_buf[-2], AsmCmd) and out_buf[-2].cmd == 'JMP':
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
                if prev_stmt.cmd == 'JMP' and prev_stmt.args[0] == curr_stmt:
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

    def allocate_vm_tags(self, tag_id_offset):
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
                        if asm_var.var_sym.context_func_sym is None:
                            global_asm_vars[asm_var] = True
                        else:
                            local_asm_vars[asm_var] = True
        
    def format_statements(self, indent, use_comments):
        asm_lines = []
        for asm_stmt in self.stmt_buf:
            asm_line = asm_stmt.format_statement(indent)
            if use_comments and asm_stmt.comment is not None:
                asm_line = '%-24s; %s' % (asm_line, asm_stmt.comment)
            asm_lines.append(asm_line)
        return asm_lines

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
    def __init__(self, ctype, cname, decl_node, context_func_sym, asm_var):
        super().__init__(ctype, cname)
        self.decl_node = decl_node
        self.context_func_sym = context_func_sym
        if asm_var is None:
            self.asm_var = AsmVar(var_sym=self)
        else:
            if asm_var.var_sym is not None:
                raise Exception('internal error: AsmVar is already bound to a VariableSymbol')
            self.asm_var = asm_var
            asm_var.var_sym = self

    def asm_repr(self):                 ## AsmVar asm_var, str() expands to VM variable name ("vN")
        return self.asm_var

class VmParameterSymbol(VariableSymbol):
    def __init__(self, ctype, cname, vm_param_id):
        super().__init__(ctype, cname)
        self.vm_param_id = vm_param_id

    def asm_repr(self):                 ## str vm_param_id, VM parameter name ("pN")
        return self.vm_param_id

class FunctionSymbol(AbstractSymbol):
    def __init__(self, cname, prototype):
        super().__init__(cname)
        self.prototype = prototype

    def decl_str(self):
        return '%s %s(%s)' % (self.prototype.ret_ctype, self.cname, ', '.join(self.prototype.arg_ctypes))

class ProgramFunctionSymbol(FunctionSymbol):
    def __init__(self, cname, prototype, decl_node):
        super().__init__(cname, prototype)
        self.decl_node = decl_node      ## c_ast.Decl, first declaration's node
        self.impl_node = None           ## None or c_ast.FuncDef, function implementation's AST node
        self.has_caller = False         ## bool, True: function has at least one caller
        self.asm_tag = AsmTag()         ## AsmTag, str() expands to function entry point's TAG
        self.asm_buf = AsmBuffer()      ## AsmBuffer, function implementation's statement buffer
        self.arg_vars = [               ## list(AsmVar), function argument VM variables
            AsmVar() for i in range(prototype.arg_count)]

    def asm_repr(self):                 ## AsmTag asm_tag, str() expands to function entry point's TAG
        return self.asm_tag

class VmApiFunctionSymbol(FunctionSymbol):
    def __init__(self, cname, prototype, vm_func_cmd):
        super().__init__(cname, prototype)
        self.vm_func_cmd = vm_func_cmd

    def asm_repr(self):                 ## str vm_func_cmd, VM's special function command name
        return self.vm_func_cmd

    def map_argument(self, node, i_arg, const_arg):
        return const_arg

class VmApiFunction_gpioSetPullUpDown(VmApiFunctionSymbol):
    def map_argument(self, node, i_arg, const_arg):
        if i_arg == 1:
            ## int gpioSetPullUpDown(unsigned gpio, unsigned pud), 2nd argument "pud":
            ##   index    | 0          | 1           | 2
            ##   vm_api.h | PI_PUD_OFF | PI_PUD_DOWN | PI_PUD_UP
            ##   PUD g p  | "O"        | "D"         | "U"
            if const_arg is None:
                raise PccError(node, '%s: compile-time constant required for 2nd argument' % self.decl_str())
            const_int = int(const_arg, 0)
            if const_int >= 0 and const_int <= 2:
                const_arg = 'ODU'[const_int]
        return const_arg

class VmApiFunction_gpioSetMode(VmApiFunctionSymbol):
    def map_argument(self, node, i_arg, const_arg):
        if i_arg == 1:
            ## int gpioSetMode(unsigned gpio, unsigned mode), 2nd argument "mode":
            ##   index     | 0        | 1         | 2       | 3       | 4       | 5       | 6       | 7
            ##   vm_api.h  | PI_INPUT | PI_OUTPUT | PI_ALT5 | PI_ALT4 | PI_ALT0 | PI_ALT1 | PI_ALT2 | PI_ALT3
            ##   MODES g m | "R"      | "W"       | "5"     | "4"     | "0"     | "1"     | "2"     | "3"
            if const_arg is None:
                raise PccError(node, '%s: compile-time constant required for 2nd argument' % self.decl_str())
            const_int = int(const_arg, 0)
            if const_int >= 0 and const_int <= 7:
                const_arg = 'RW540123'[const_int]
        return const_arg

class HelperFunction:
    def __init__(self, func_name):
        self.func_name = func_name      ## str, internal helper function name
        self.asm_tag = AsmTag()         ## AsmTag, helper function entry point's TAG
        self.asm_buf = AsmBuffer()      ## AsmBuffer, helper function implementation's statement buffer

class FunctionPrototype:
    def __init__(self, decl_node, is_extern):
        arg_ctypes = []
        func_args = decl_node.type.args
        if func_args is not None and not (len(func_args.params) == 1 and
                self._parse_ctype(func_args.params[0].type, accept_void=True, accept_uint=is_extern) == 'void'):
            for arg in func_args.params:
                arg_ctypes.append(self._parse_ctype(arg.type, accept_uint=is_extern))
        self.is_extern = is_extern
        self.ret_ctype = self._parse_ctype(decl_node.type.type, accept_void=True, accept_uint=is_extern)
        self.arg_ctypes = arg_ctypes
        self.arg_count = len(arg_ctypes)
        self.has_return = self.ret_ctype != 'void'

    def matches(self, other):
        return self.is_extern == other.is_extern and \
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
            raise PccError(node.type, 'unsupported type "%s"' % ' '.join(type_names))
        raise PccError(node.type, 'unsupported type')

## ---------------------------------------------------------------------------

class Pcc:
    def __init__(self, c_files, debug):
        self.c_source_files = c_files       ## dict(str filename: list(str c_src_line)), unmodified C sources for error reports
        self.debug = debug                  ## bool, True: show extra debug output
        self.error_count = 0                ## int, error counter
        self.var_count = None               ## int, number of VM variables allocated
        self.tag_count = None               ## int, number of VM tags allocated
        self.asm_buf = AsmBuffer()          ## AsmBuffer, root output buffer
        self.asm_out = self.asm_buf         ## AsmBuffer, current output buffer
        self.scope = collections.ChainMap() ## ChainMap, current scope with chained parents
        self.context_func_sym = None        ## None or ProgramFunctionSymbol, current function context
        self.loop_tag_stack = []            ## list(), stack of loop AsmTag contexts
        self.loop_continue_tag = None       ## None or AsmTag, current tag to JMP to in case of a "continue" statement
        self.loop_break_tag = None          ## None or AsmTag, current tag to JMP to in case of a "break" statement
        self.declared_prog_func = set()     ## set(ProgramFunctionSymbol func_sym), all declared program functions
        self.helper_functions = {}          ## dict(str func_name: HelperFunction hlp_func), set of internal helper functions
        self.log_error_location = None      ## most recent reported error location
        self.all_asm_bufs = None            ## list(AsmBuf asm_buf, ...), list of all buffers
        self.all_asm_vars = None            ## list(AsmVar asm_var, ...), list of all variables

    def compile(self, root_node, do_reduce=True):
        prog_functions = []                 ## list(ProgramFunctionSymbol func), all implemented program functions
        ## compile top-level declarations and program functions
        for node in root_node:
            try:
                if isinstance(node, c_ast.Decl):
                    self.compile_Decl_node(node)
                elif isinstance(node, c_ast.FuncDef):
                    func_sym = self.compile_function_definition(node)
                    prog_functions.append(func_sym)
                else:
                    raise PccError(node, 'unsupported syntax')
            except PccError as e:
                self.log_error(e)
        ## check user defined functions
        main_func = self.find_symbol('main', filter=ProgramFunctionSymbol)
        if main_func is None:
            self.log_error(PccError(None, 'missing main() function implementation'))
        else:
            main_func.has_caller = True
        for prog_func in self.declared_prog_func:
            if prog_func.has_caller and prog_func.impl_node is None:
                ## check that all called user defined functions are actually defined
                self.log_error(PccError(prog_func.decl_node,
                    'function "%s" declared without implementation' % prog_func.cname))
            elif not prog_func.has_caller:
                ## drop unused functions
                prog_functions.remove(prog_func)
        if self.error_count == 0:
            ## append main() CALL to init segment
            self.asm_buf('CALL', main_func.asm_tag, comment='main()')
            self.asm_buf('HALT')
            ## compile helper functions
            self.compile_helper_function_impl()
            all_functions = prog_functions + list(self.helper_functions.values())
            self.all_asm_bufs = [self.asm_buf] + [f.asm_buf for f in all_functions]
            ## drop unused tags in program functions
            tags = dict() ## dict(AsmTag asm_tag: int use_count), preseed w. program/helper functions
            for func_sym in all_functions:
                tags[func_sym.asm_tag] = 1
            for func in prog_functions:
                func.asm_buf.drop_unused_tags(tags.copy())
            ## reduce program functions
            if do_reduce:
                for func in prog_functions:
                    func.asm_buf.reduce()
            ## bind VM tags
            tag_count = 0
            tag_cursor = 10
            for func in all_functions:
                n_tags = func.asm_buf.allocate_vm_tags(tag_cursor)
                tag_count += n_tags
                tag_cursor = ((tag_cursor + n_tags + 10) // 10) * 10
            self.tag_count = tag_count
            ## bind VM variables
            global_asm_vars = dict()
            local_asm_vars = dict()
            for asm_buf in self.all_asm_bufs:
                asm_buf.collect_vm_variables(global_asm_vars, local_asm_vars)
            var_cursor = 1 + len(ARG_REGS)
            for asm_var in global_asm_vars.keys():
                asm_var.bind(var_cursor)
                var_cursor += 1
            for asm_var in local_asm_vars.keys():
                asm_var.bind(var_cursor)
                var_cursor += 1
            self.var_count = var_cursor
            self.all_asm_vars = list(global_asm_vars.keys())
            self.all_asm_vars.extend(local_asm_vars.keys())
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
                asm_lines.append(asm_var.format_decl_comment())
        for asm_buf in self.all_asm_bufs:
            if len(asm_lines) > 0:
                asm_lines.append('')
            asm_lines.extend(asm_buf.format_statements('    ', use_comments))
        result = '\n'.join(asm_lines)
        if file is not None:
            print(result, file=file)
        return result

    ## Private functions

    def log_error(self, e, context_func_sym=None):
        self._log_message(e.node, 'error: %s' % str(e), context_func_sym)
        if e.node is not None and self.debug:
            print('Extra debug node information:\n' + str(e.node), file=sys.stderr)
        self.error_count += 1

    def log_warning(self, node, message, context_func_sym):
        self._log_message(node, 'warning: %s' % message, context_func_sym)

    def _log_message(self, node, message, context_func_sym):
        if context_func_sym is not None:
            e_location = (context_func_sym.impl_node.coord.file, context_func_sym.cname)
            if self.log_error_location != e_location:
                self.log_error_location = e_location
                print('%s: In function "%s":' % e_location, file=sys.stderr)
        if node is None:
            print(message, file=sys.stderr)
        else:
            coord = node.coord
            print('%s: %s' % (coord, message), file=sys.stderr)
            print(format_src_quote(self.c_source_files, coord.file, coord.line, coord.column), file=sys.stderr)

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
            raise PccError(node, 'redefinition of "%s"' % sym_obj.cname)
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
        return self.bind_symbol(node, VmVariableSymbol(ctype, cname, node, self.context_func_sym, asm_var))

    def declare_parameter(self, node, ctype, cname):
        m = re.fullmatch('(?:.*_)?(p[0-9])(?:_.*)?', cname)
        if not m:
            raise PccError(node, '%s: external variable names must contain one of "p0", "p1", ..., "p9"' % cname)
        vm_param_name = m.groups(0)[0]
        return self.bind_symbol(node, VmParameterSymbol(ctype, cname, vm_param_name))

    def declare_function(self, node, is_extern=False):
        func_name = node.name
        prototype = FunctionPrototype(node, is_extern)
        ## check main() prototype constraints
        if func_name == 'main':
            if prototype.has_return:
                raise PccError(node, 'return type other than "void" is not supported for main()')
            elif prototype.arg_count > 0:
                raise PccError(node, 'function arguments are not supported for main()')
        func_sym = self.find_symbol(func_name, filter=FunctionSymbol)
        if func_sym is not None:
            ## check for function prototype redeclaration
            if not prototype.matches(func_sym.prototype):
                raise PccError(node, 'function prototype conflicts with previous declaration')
            return func_sym
        else:
            ## create function symbol and bind to current scope
            if is_extern:
                if func_name not in VM_FUNCTION_CMD:
                    raise PccError(node, 'unknown VM function name "%s"' % func_name)
                vm_func_cmd = VM_FUNCTION_CMD[func_name]
                if func_name == 'gpioSetPullUpDown':
                    func_sym = VmApiFunction_gpioSetPullUpDown(func_name, prototype, vm_func_cmd)
                elif func_name == 'gpioSetMode':
                    func_sym = VmApiFunction_gpioSetMode(func_name, prototype, vm_func_cmd)
                else:
                    func_sym = VmApiFunctionSymbol(func_name, prototype, vm_func_cmd)
            else:
                func_sym = ProgramFunctionSymbol(func_name, prototype, node)
                self.declared_prog_func.add(func_sym)
            return self.bind_symbol(node, func_sym)

    def declare_helper_function(self, node, func_name):
        if func_name in self.helper_functions:
            hlp_func = self.helper_functions[func_name]
        else:
            if func_name not in HELPER_FUNCTION_DESCR:
                raise Exception('internal error: unknown helper function name "%s"' % func_name)
            hlp_func = HelperFunction(func_name)
            self.helper_functions[func_name] = hlp_func
        return hlp_func

    def try_parse_constant(self, node):
        result = None
        if isinstance(node, c_ast.Constant):
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
                raise PccError(node, 'variable "%s" undeclared' % node.name)
            result = var_sym.asm_repr()
        return result

    ## Code-generating functions

    def compile_expression(self, node, dst_reg=None):   ## A := eval(expr), F: undefined!
        node_term = self.try_parse_term(node)
        if node_term is not None:
            self.asm_out('LDA', node_term)
        elif isinstance(node, c_ast.UnaryOp):
            self.compile_UnaryOp_node(node)
        elif isinstance(node, c_ast.BinaryOp):
            self.compile_BinaryOp_node(node)
        elif isinstance(node, c_ast.FuncCall):
            self.compile_FuncCall_node(node)
        else:
            raise PccError(node, 'unsupported expression syntax')
        if dst_reg is not None:
            self.asm_out('STA', dst_reg)

    def compile_assignment(self, dst_reg, rhs_node, assign_op='='):
        rhs_term = self.try_parse_term(rhs_node)
        if assign_op == '=':
            if rhs_term is not None:
                self.asm_out('LD', dst_reg, rhs_term)
            else:
                self.compile_expression(rhs_node, dst_reg=dst_reg)
        elif assign_op[:-1] in VM_BINARY_ARITHMETIC_OP:
            operator = VM_BINARY_ARITHMETIC_OP[assign_op[:-1]]
            if rhs_term is not None:
                self.asm_out('LDA', dst_reg)
                self.asm_out(operator, rhs_term)
            else:
                self.compile_expression(rhs_node, dst_reg=SCR0)
                self.asm_out('LDA', dst_reg)
                self.asm_out(operator, SCR0)
            self.asm_out('STA', dst_reg)
        else:
            raise PccError(rhs_node, 'unsupported assignment operator "%s"' % assign_op)

    def compile_function_definition(self, node):
        func_sym = self.declare_function(node.decl)     ## ProgramFunctionSymbol func_sym
        func_sym.impl_node = node
        self.context_func_sym = func_sym
        self.asm_out = func_sym.asm_buf
        self.push_scope()
        try:
            self.asm_out('TAG', func_sym.asm_tag, comment=func_sym.decl_str())
            if func_sym.prototype.arg_count > 0:
                arg_vars = func_sym.arg_vars
                arg_ctypes = func_sym.prototype.arg_ctypes
                for i_arg, arg_param in enumerate(node.decl.type.args.params):
                    arg_ctype = arg_ctypes[i_arg]
                    arg_cname = arg_param.name
                    if arg_cname is None:
                        arg_cname = '00_%s$%d' % (func_sym.cname, i_arg)
                    self.declare_variable(node.body, arg_ctype, arg_cname, asm_var=arg_vars[i_arg])
            terminated = self.compile_Compound_node(node.body)
            if not terminated:
                if func_sym.prototype.has_return:
                    self.log_warning(node, 'function "%s" should return a value' %
                        func_sym.decl_str(), func_sym)
                self.asm_out('RET')
        except PccError as e:
            self.log_error(e, context_func_sym=func_sym)
        finally:
            self.pop_scope()
            self.asm_out = self.asm_buf
            self.context_func_sym = None
        return func_sym

    def compile_statement(self, node):
        ast_class_name = node.__class__.__name__
        compile_method = getattr(self, 'compile_%s_node' % ast_class_name, None)
        if not callable(compile_method):
            raise PccError(node, '%s: unsupported statement syntax' % ast_class_name)
        return compile_method(node)

    def compile_UnaryOp_node(self, node):
        if node.op in ('++', '--', 'p++', 'p--') and isinstance(node.expr, c_ast.ID):
            reg_sym = self.find_symbol(node.expr.name, filter=VariableSymbol)
            if reg_sym is None:
                raise PccError(node.expr, 'variable "%s" undeclared' % node.expr.name)
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
                self.asm_out('LDA', SCR0)           ## A := SCR0, F := (A - 1)!
            elif node.op == 'p--':                  ## Postfix decrement "X--":
                self.asm_out('LD', SCR0, vm_reg)    ## SCR0 := X
                self.asm_out('DCR', vm_reg)         ## --X, F := X
                self.asm_out('LDA', SCR0)           ## A := SCR0
        elif node.op in ('!', '~', '+', '-'):
            self.compile_expression(node.expr)
            if node.op == '-':                      ## flip sign: NEG()
                self.compile_helper_function_call(node, 'NEG')
            elif node.op == '!':                    ## logical NOT: NOTL()
                self.compile_helper_function_call(node, 'NOTL')
            elif node.op == '~':                    ## bitwise NOT: NOT(), inline
                self.asm_out('XOR', '0xffffffff')   ## A := A ^ 0xffffffff; F := A
            elif node.op == '+':                    ## A := +A (NOP)
                pass
        else:
            raise PccError(node, 'unsupported unary operator "%s"' % node.op)
        return False

    def compile_BinaryOp_node(self, node):
        is_helper_op = node.op in VM_BINARY_LOGICAL_OP
        if node.op not in VM_BINARY_ARITHMETIC_OP and not is_helper_op:
            raise PccError(node, 'unsupported binary operator "%s"' % node.op)
        operator = VM_BINARY_LOGICAL_OP[node.op] if is_helper_op else VM_BINARY_ARITHMETIC_OP[node.op]
        ## compile left-hand side (lhs) into ACC
        self.compile_expression(node.left)
        ## compile right-hand side (rhs) and combine with lhs using <operator>
        rhs_term = self.try_parse_term(node.right)
        if rhs_term is not None:
            if is_helper_op:
                self.asm_out('LD', SCR0, rhs_term)
                self.compile_helper_function_call(node.right, operator) ## A := A <OP> SCR0, F := undefined!
            else:
                self.asm_out(operator, rhs_term)    ## A := A <OP> x, F := A
        else:
            self.asm_out('PUSHA')                   ## save ACC (lhs) on stack
            self.compile_expression(node.right, dst_reg=SCR0)   ## compile rhs into SCR0
            self.asm_out('POPA')                    ## restore lhs in ACC from stack    
            if is_helper_op:
                self.compile_helper_function_call(node.right, operator) ## A := A <OP> SCR0, F := undefined!
            else:
                self.asm_out(operator, SCR0)        ## A := A <OP> SCR0, F := A
        return False

    def compile_Decl_node(self, node):
        if len(node.align) != 0 or node.bitsize is not None or len(node.funcspec) != 0:
            raise PccError(node, 'unsupported declaration syntax')
        is_extern = False
        if len(node.storage) > 0:
            if len(node.storage) != 1 or node.storage[0] != 'extern':
                raise PccError(node, 'unsupported storage qualifier "%s"' % ' '.join(node.storage))
            is_extern = True
        decl_type = node.type
        if isinstance(decl_type, c_ast.TypeDecl):
            if len(decl_type.quals) != 0:
                raise PccError(node, 'unsupported type qualifier "%s"' % ' '.join(decl_type.quals))
            if isinstance(decl_type.type, c_ast.IdentifierType):
                if len(decl_type.type.names) == 1 and decl_type.type.names[0] in ('int', 'long'):
                    var_ctype = decl_type.type.names[0]
                else:
                    raise PccError(node, 'unsupported variable type "%s"' % (' '.join(decl_type.type.names)))
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
            self.declare_function(node, is_extern=is_extern)
        elif isinstance(decl_type, c_ast.Enum):
            self.declare_enum(decl_type)
        else:
            raise PccError(node, 'unsupported declaration syntax')
        return False

    def compile_Assignment_node(self, node):
        lhs_sym = self.find_symbol(node.lvalue.name, filter=VariableSymbol)
        if lhs_sym is None:
            raise PccError(node.lvalue, 'variable "%s" undeclared' % node.lvalue.name)
        lhs_reg = lhs_sym.asm_repr()
        self.compile_assignment(lhs_reg, node.rvalue, assign_op=node.op)
        return False

    def compile_FuncCall_node(self, node, dst_reg=None):
        terminated = False
        func_name = node.name.name
        func_sym = self.find_symbol(func_name, filter=FunctionSymbol)
        if func_sym is None:
            raise PccError(node, 'function "%s" undeclared' % func_name)
        elif dst_reg is not None and not func_sym.prototype.has_return:
            raise PccError(node, 'function "%s" declared without return value' % func_sym.decl_str())
        arg_count = len(node.args.exprs) if node.args is not None else 0
        if func_sym.prototype.arg_count != arg_count:
            raise PccError(node, 'function "%s" expects %d argument(s) instead of %d' % (
                func_sym.decl_str(), func_sym.prototype.arg_count, arg_count))
        if isinstance(func_sym, VmApiFunctionSymbol):
            ## compile call to VM API function
            args = []
            for i_arg in range(func_sym.prototype.arg_count):
                arg_expr_node = node.args.exprs[i_arg]
                arg_term = func_sym.map_argument(arg_expr_node, i_arg, self.try_parse_constant(arg_expr_node))
                if arg_term is None:
                    arg_term = self.try_parse_term(arg_expr_node)
                if arg_term is None:
                    arg_term = ARG_REGS[i_arg]
                    self.compile_assignment(arg_term, arg_expr_node)
                args.append(arg_term)
            if func_sym.vm_func_cmd == 'HALT':
                terminated = True
            self.asm_out(func_sym.vm_func_cmd, *args, comment='%s()' % func_name)
        else:
            ## compile call to user defined function
            func_sym.has_caller = True
            for i_arg in range(func_sym.prototype.arg_count):
                arg_asm_var = func_sym.arg_vars[i_arg]
                arg_expr = node.args.exprs[i_arg]
                self.compile_assignment(arg_asm_var, arg_expr)
            self.asm_out('CALL', func_sym.asm_tag, comment='%s()' % func_name)
        if dst_reg is not None:
            self.asm_out('STA', dst_reg)
        return terminated

    def compile_Compound_node(self, node):
        terminated = False
        if node.block_items is not None:
            self.push_scope()
            try:
                in_unreachable_code = False
                for statement_node in node.block_items:
                    if in_unreachable_code:
                        self.log_warning(statement_node, 'unreachable code', self.context_func_sym)
                        break
                    s_terminated = self.compile_statement(statement_node)
                    if s_terminated:
                        terminated = True
                    if s_terminated or isinstance(statement_node, (c_ast.Continue, c_ast.Break)):
                        in_unreachable_code = True
            finally:
                self.pop_scope()
        return terminated

    def compile_Return_node(self, node):
        ret_val_expected = self.context_func_sym.prototype.has_return
        ret_val_given = node.expr is not None
        if ret_val_given and not ret_val_expected:
            self.log_warning(node, 'function "%s" should not return a value' %
                self.context_func_sym.decl_str(), self.context_func_sym)
        elif not ret_val_given and ret_val_expected:
            self.log_warning(node, 'function "%s" should return a value' %
                self.context_func_sym.decl_str(), self.context_func_sym)
        elif ret_val_given:
            self.compile_expression(node.expr)
        self.asm_out('RET')
        return True

    def compile_If_node(self, node):
        else_tag = AsmTag() if node.iffalse is not None else None
        endif_tag = AsmTag()
        self.compile_expression(node.cond)          ## A := compile(expr)
        self.asm_out('OR', 0, comment='F=A')        ## assert F := A before conditional jump
        if else_tag is None:
            self.asm_out('JZ', endif_tag)           ## IF expr == FALSE AND no-else-branch GOTO endif_tag
        else:
            self.asm_out('JZ', else_tag)            ## IF expr == FALSE AND has-else-branch GOTO else_tag
        t1 = self.compile_statement(node.iftrue)    ## compile if-branch statement(s)
        t2 = False
        if else_tag is not None:
            if not t1:                              ## omit the following JMP when if-branch terminated (RET)
                self.asm_out('JMP', endif_tag)      ## IF has-else-branch GOTO endif_tag
            self.asm_out('TAG', else_tag)           ## TAG: else_tag
            t2 = self.compile_statement(node.iffalse)   ## compile else-branch
        self.asm_out('TAG', endif_tag)              ## TAG: endif_tag
        return t1 and t2

    def compile_While_node(self, node):
        begin_tag = AsmTag()
        end_tag = AsmTag()
        self.push_loop_tags(begin_tag, end_tag)
        try:
            self.asm_out('TAG', begin_tag)          ## TAG: begin_tag
            self.compile_expression(node.cond)      ## A := compile(expr)
            self.asm_out('OR', 0, comment='F=A')    ## assert F := A before conditional jump
            self.asm_out('JZ', end_tag)             ## expr == FALSE => end_tag
            trm = self.compile_statement(node.stmt) ## compile statement(s)
            self.asm_out('JMP', begin_tag)          ## => begin_tag
            self.asm_out('TAG', end_tag)            ## TAG: end_tag
        finally:
            self.pop_loop_tags()
        return trm

    def compile_DoWhile_node(self, node):
        begin_tag = AsmTag()
        end_tag = AsmTag()
        self.push_loop_tags(begin_tag, end_tag)
        try:
            self.asm_out('TAG', begin_tag)          ## TAG: begin_tag
            trm = self.compile_statement(node.stmt) ## compile statement(s)
            self.compile_expression(node.cond)      ## A := compile(expr)
            self.asm_out('OR', 0, comment='F=A')    ## assert F := A before conditional jump
            self.asm_out('JNZ', begin_tag)          ## expr == TRUE => begin_tag
            self.asm_out('TAG', end_tag)            ## TAG: end_tag
        finally:
            self.pop_loop_tags()
        return trm

    def compile_For_node(self, node):
        begin_tag = AsmTag()
        next_tag = AsmTag()
        end_tag = AsmTag()
        self.push_loop_tags(next_tag, end_tag)
        try:
            needs_local_scope = node.init is not None and isinstance(node.init, c_ast.DeclList)
            if needs_local_scope:
                self.push_scope()
            try:
                if node.init is not None:               ## compile init-clause statement(s)
                    if isinstance(node.init, c_ast.DeclList):
                        for decl_node in node.init.decls:
                            self.compile_Decl_node(decl_node)
                    else:
                        self.compile_statement(node.init)
                self.asm_out('TAG', begin_tag)          ## TAG: begin_tag
                if node.cond is not None:
                    self.compile_expression(node.cond)  ## compile cond-expression, A := compile(cond)
                    self.asm_out('OR', 0, comment='F=A') ## assert F := A before conditional jump
                    self.asm_out('JZ', end_tag)         ## cond == FALSE => end_tag
                trm = self.compile_statement(node.stmt) ## compile loop-body statement(s)
                self.asm_out('TAG', next_tag)           ## TAG: next_tag
                if node.next is not None:               ## compile iteration-expression(s)
                    if isinstance(node.next, c_ast.ExprList):
                        for expr_node in node.next.exprs:
                            self.compile_expression(expr_node)
                    else:
                        self.compile_expression(node.next)
                self.asm_out('JMP', begin_tag)          ## => begin_tag
                self.asm_out('TAG', end_tag)            ## TAG: end_tag
            finally:
                if needs_local_scope:
                    self.pop_scope()
        finally:
            self.pop_loop_tags()
        return trm

    def compile_Continue_node(self, node):
        if self.loop_continue_tag is None:
            raise PccError(node, '"continue" outside loop not allowed')
        self.asm_out('JMP', self.loop_continue_tag)
        return False

    def compile_Break_node(self, node):
        if self.loop_break_tag is None:
            raise PccError(node, '"break" outside loop not allowed')
        self.asm_out('JMP', self.loop_break_tag)
        return False

    def compile_EmptyStatement_node(self, node):
        return False

    ## Helper functions

    def compile_helper_function_call(self, node, func_name):
        hlp_func = self.declare_helper_function(node, func_name)
        self.asm_out('CALL', hlp_func.asm_tag, comment=func_name)

    def compile_helper_function_impl(self):
        for func_name, helper_func in self.helper_functions.items():
            if func_name not in HELPER_FUNCTION_DESCR:
                raise Exception('internal error: unexpected helper function name "%s"' % func_name)
            comment = HELPER_FUNCTION_DESCR[func_name]
            asm_out = helper_func.asm_buf
            asm_out('TAG', helper_func.asm_tag, comment=comment)
            if func_name == 'NEG':
                asm_out('XOR', '0xffffffff')
                asm_out('ADD', 1)
                asm_out('RET')
            elif func_name == 'NOTL':
                true_tag = AsmTag()
                asm_out('OR', 0, comment='F=A')    ## assert F := A before conditional jump
                asm_out('JZ', true_tag)            ## IF (F == 0) GOTO true_tag
                asm_out('LDA', 0)
                asm_out('RET')                     ## return FALSE
                asm_out('TAG', true_tag)           ## true_tag:
                asm_out('LDA', 1)
                asm_out('RET')                     ## return TRUE
            elif func_name == 'ANDL':
                ret_tag = AsmTag()
                asm_out('OR', 0, comment='F=A')    ## assert F := A before conditional jump
                asm_out('JZ', ret_tag)             ## IF (F == 0) GOTO ret_tag
                asm_out('LDA', SCR0)
                asm_out('OR', 0, comment='F=A')    ## assert F := A before conditional jump
                asm_out('JZ', ret_tag)             ## IF (F == 0) GOTO ret_tag
                asm_out('LDA', 1)
                asm_out('TAG', ret_tag)            ## ret_tag:
                asm_out('RET')                     ## return TRUE or FALSE
            elif func_name == 'ORL':
                true_tag = AsmTag()
                asm_out('OR', SCR0)                ## A := A | SCR0, F := A
                asm_out('JNZ', true_tag)           ## IF (F != 0) GOTO true_tag
                asm_out('RET')                     ## return FALSE
                asm_out('TAG', true_tag)           ## true_tag:
                asm_out('LDA', 1)
                asm_out('RET')                     ## return TRUE
            elif func_name == 'EQ':
                true_tag = AsmTag()
                asm_out('CMP', SCR0)               ## F := A - SCR0
                asm_out('JZ', true_tag)            ## IF (F == 0) GOTO true_tag
                asm_out('LDA', 0)
                asm_out('RET')                     ## return FALSE
                asm_out('TAG', true_tag)           ## true_tag:
                asm_out('LDA', 1)
                asm_out('RET')                     ## return TRUE
            elif func_name == 'NE':
                true_tag = AsmTag()
                asm_out('CMP', SCR0)               ## F := A - SCR0
                asm_out('JNZ', true_tag)           ## IF (F != 0) GOTO true_tag
                asm_out('LDA', 0)                  ## A := 0
                asm_out('RET')                     ## return FALSE
                asm_out('TAG', true_tag)           ## true_tag:
                asm_out('LDA', 1)                  ## A := 1
                asm_out('RET')                     ## return TRUE
            elif func_name == 'GT':
                false_tag = AsmTag()
                asm_out('CMP', SCR0)               ## F := A - SCR0
                asm_out('JZ', false_tag)           ## IF (F == 0) GOTO false_tag
                asm_out('JM', false_tag)           ## IF (F < 0) GOTO false_tag
                asm_out('LDA', 1)
                asm_out('RET')                     ## return TRUE
                asm_out('TAG', false_tag)          ## false_tag:
                asm_out('LDA', 0)
                asm_out('RET')                     ## return FALSE
            elif func_name == 'GE':
                true_tag = AsmTag()
                asm_out('CMP', SCR0)               ## F := A - SCR0
                asm_out('JP',  true_tag)           ## IF (F >= 0) GOTO true_tag
                asm_out('LDA', 0)
                asm_out('RET')                     ## return FALSE
                asm_out('TAG', true_tag)           ## true_tag:
                asm_out('LDA', 1)
                asm_out('RET')                     ## return TRUE
            elif func_name == 'LT':
                true_tag = AsmTag()
                asm_out('CMP', SCR0)               ## F := A - SCR0
                asm_out('JM',  true_tag)           ## IF (F < 0) GOTO true_tag
                asm_out('LDA', 0)
                asm_out('RET')                     ## return FALSE
                asm_out('TAG', true_tag)           ## true_tag:
                asm_out('LDA', 1)
                asm_out('RET')                     ## return TRUE
            elif func_name == 'LE':
                true_tag = AsmTag()
                asm_out('CMP', SCR0)               ## F := A - SCR0
                asm_out('JZ', true_tag)            ## IF (F == 0) GOTO true_tag
                asm_out('JM', true_tag)            ## IF (F < 0) GOTO true_tag
                asm_out('LDA', 0)
                asm_out('RET')                     ## return FALSE
                asm_out('TAG', true_tag)           ## true_tag:
                asm_out('LDA', 1)
                asm_out('RET')                     ## return TRUE

## ---------------------------------------------------------------------------

def pcc(filenames, debug=False, do_reduce=True):
    VM_API_H = 'vm_api.h'
    if VM_API_H not in [PurePath(filename).name for filename in filenames]:
        filenames = [VM_API_H] + filenames
    for filename in filenames:
        if not Path(filename).is_file():
            print('%s: error: file not found' % filename, file=sys.stderr)
            return None

    c_source_files = {}
    ast = None
    cparser = CParser()
    for filename in filenames:
        with open(filename, 'r') as f:
            c_source_lines = list(line.rstrip('\r\n') for line in f.readlines())
        c_source_files[filename] = c_source_lines
        ## drop C-style comments
        c_source = '\n'.join(c_source_lines)
        c_source = re.sub(r'//.*', '', c_source)
        c_source = re.sub(r'/\*(.|\n)*?\*/', lambda m: re.sub(r'.*', '', m.group(0)), c_source)
        try:
            if ast is None:
                ast = cparser.parse(c_source, filename)
            else:
                ast.ext += cparser.parse(c_source, filename).ext
        except ParseError as e:
            print(e, file=sys.stderr)
            m = re.fullmatch('([^:]+):(\d+):(\d+):.+', str(e))
            if m:
                filename, row, col = m[1], int(m[2]), int(m[3])
                print(format_src_quote(c_source_files, filename, row, col), file=sys.stderr)
            print('*** aborted with parser error', file=sys.stderr)
            return None

    cc = Pcc(c_source_files, debug)
    if cc.compile(ast, do_reduce=do_reduce) != 0:
        print('*** aborted with compiler error(s)', file=sys.stderr)
        return None
    return cc

def main():
    parser = argparse.ArgumentParser(description='pcc - PIGS C compiler')
    parser.add_argument('filenames', metavar='C_FILE', nargs='+', help='filenames to parse')
    parser.add_argument('-o', metavar='FILE', help='place the output into FILE ("-" for STDOUT)')
    parser.add_argument('-c', dest='comments', action='store_true', help='add comments to asm output')
    parser.add_argument('-n', dest='no_reduce', action='store_true', help='do not reduce asm output')
    parser.add_argument('-d', dest='debug', action='store_true', help='add debug output to error messages')
    args = parser.parse_args()

    cc = pcc(args.filenames, debug=args.debug, do_reduce=not args.no_reduce)
    if cc is None:
        return -1
    out_filename = args.o
    if out_filename is None:
        out_filename = PurePath(args.filenames[-1]).stem + '.s'
    if out_filename == '-':
        cc.encode_asm(use_comments=args.comments, file=sys.stdout)
    else:
        with open(out_filename, 'w') as f:
            cc.encode_asm(use_comments=args.comments, file=f)
    print('\nVM variables used: %d/150, tags: %d/50.' % (cc.var_count, cc.tag_count), file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
