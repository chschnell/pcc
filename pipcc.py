#!/usr/bin/env python3
##
## pipcc.pi
## Runs pcc and executes asm script on a Raspberry Pi.
##
## Requirements:
##   pip install pigpio
##

import sys, re, argparse, configparser
from time import time, sleep
from pathlib import PurePath, Path

import pigpio

sys.path.extend(str(Path(__file__).resolve().parent))
from pcc import pcc

def parse_parameter(p_str):
    if p_str is not None:
        parameter = [int(p) for p in p_str.strip('[]').split(',')[:10]]
        if len(parameter) > 0:
            return parameter + [0] * (10 - len(parameter))
    return None

def format_parameter(p):
    return f'[{p[0]}, {p[1]}, {p[2]}, {p[3]}, {p[4]}, {p[5]}, {p[6]}, {p[7]}, {p[8]}, {p[9]}]'

class PiPcc:
    def __init__(self, use_cis, hostname=None, port=8888, do_reduce=True):
        self.use_cis = use_cis
        self.hostname = hostname
        self.port = port
        self.do_reduce = do_reduce
        self.out_parameter = None
        self.pi = None
        self.t0 = time()

    def run(self, filenames, asm_input=False, in_parameter=None, out_parameter=None, timeout_sec=None):
        self.out_parameter = []
        ## connect pigpiod
        pi = self.pigpiod_connect()
        if pi is None:
            return 1
        ## load or compile asm_code
        asm_code = None
        if asm_input:
            asm_filename = filenames[0]
            asm_code = self.load_asm_source(asm_filename)
        else:
            asm_filename = PurePath(filenames[-1]).stem + '.s'
            cc_result = pcc(filenames, use_cis=self.use_cis, do_reduce=self.do_reduce)
            if cc_result is not None:
                self.log_message(f'{asm_filename}: VM variables used: {cc_result.var_count}/150, tags: {cc_result.tag_count}/50')
                asm_code = cc_result.asm_code
        if asm_code is None:
            return 1
        ## upload and run asm_code
        asm_sid = pi.store_script(asm_code.encode('utf-8'))
        try:
            t1 = time()
            run_result = pi.run_script(asm_sid, in_parameter)
            if run_result != 0:
                print(f'*** {asm_filename}: run_script() failed with error {run_result}', file=sys.stderr)
                return 1
            while True:
                sleep(0)
                if pi.script_status(asm_sid)[0] == pigpio.PI_SCRIPT_HALTED:
                    break
                elif timeout_sec is not None and time() - t1 > timeout_sec:
                    self.log_message(f'{asm_filename}: script timed out, stopping...')
                    break
            status = pi.stop_script(asm_sid)
            if status != pigpio.PI_SCRIPT_INITING:
                self.log_message(f'{asm_filename}: not terminated (status: {status}), stopping...')
            else:
                p = pi.script_status(asm_sid)[1]
                self.out_parameter = list(p)
                out_parameter_str = format_parameter(p)
                if out_parameter is not None:
                    if self.out_parameter != out_parameter:
                        self.log_message(f'{asm_filename}: error: unexpected output parameter:')
                        self.log_message(f'    expected: {format_parameter(out_parameter)}')
                        self.log_message(f'    returned: {out_parameter_str}')
                        return 1
                    success_msg = 'passed'
                else:
                    success_msg = 'ok'
                self.log_message(f'{asm_filename}: {success_msg}: {out_parameter_str}')
        finally:
            pi.delete_script(asm_sid)
        return 0

    def run_testsuite(self, ts_filename):
        config = configparser.ConfigParser()
        config.read(ts_filename)
        n_sections = len(config.sections())
        for i_section, section_name in enumerate(config.sections()):
            section = config[section_name]
            if 'c_file' not in section:
                print(f'*** error: missing required parameter "c_file" in section [{section_name}]', file=sys.stderr)
                return 1
            c_file = section.get('c_file')
            c_filepath = str(Path(ts_filename).with_name(c_file))
            param_in = parse_parameter(section.get('param_in', None))
            param_out = parse_parameter(section.get('param_out', None))
            timeout_sec = section.getint('timeout_sec', None)
            self.log_message(f'[{i_section+1}/{n_sections}] {c_file}')
            if self.run([c_filepath], in_parameter=param_in, out_parameter=param_out, timeout_sec=timeout_sec) != 0:
                return 1
        return 0

    ## private methods

    P_ASM_COMMENT = re.compile(r';.*')

    def log_message(self, message):
        print(f'{time()-self.t0:-4.3f} {message}', file=sys.stderr)

    def pigpiod_connect(self):
        if self.pi is None:
            if self.hostname is None:
                self.pi = pigpio.pi()
            else:
                self.pi = pigpio.pi(self.hostname, self.port)
            if not self.pi.connected:
                return None
        return self.pi

    def load_asm_source(self, asm_filename):
        try:
            with open(asm_filename, 'r') as f:
                asm_lines = list(self.P_ASM_COMMENT.sub('', line) for line in f.readlines())
            return ''.join(asm_lines)
        except OSError as e:
            print(str(e), file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description='pipcc - PIGS C compiler and runner')
    parser.add_argument('filenames', metavar='FILE', nargs='+', help='filenames to parse')
    parser.add_argument('-e', dest='use_cis', action='store_false', help='use extended instruction set')
    parser.add_argument('-n', dest='do_reduce', action='store_false', help='do not reduce compiled asm code')
    parser.add_argument('-p', dest='parameter', help='script input parameter, comma-separated list of int')
    parser.add_argument('-t', dest='timeout', help='script timeout in seconds')
    parser.add_argument('-i', dest='hostname', metavar='HOSTNAME', help='hostname or IP address of pigpiod')
    parser.add_argument('-o', dest='port', metavar='PORT', default=8888, help='port number of pigpiod (default: 8888)')
    parser.add_argument('-s', dest='testsuite', action='store_true', help='execute testsuite FILE')
    parser.add_argument('-a', dest='assembler', action='store_true', help='treat input as assembly language file')
    args = parser.parse_args()

    pipcc = PiPcc(args.use_cis, hostname=args.hostname, port=args.port, do_reduce=args.do_reduce)
    try:
        if args.testsuite:
            result = pipcc.run_testsuite(args.filenames[0])
        else:
            result = pipcc.run(
                args.filenames,
                asm_input = args.assembler,
                in_parameter = parse_parameter(args.parameter),
                timeout_sec = args.timeout)
        if result != 0:
            print('*** aborted with error', file=sys.stderr)
    except KeyboardInterrupt:
        print('\nAborted with CTRL+C', file=sys.stderr)
        result = 1
    return result

if __name__ == '__main__':
    sys.exit(main())
