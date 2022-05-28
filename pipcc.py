#!/bin/python3m
##
## pipcc.pi
## Runs pcc and executes asm script on a Raspberry Pi.
##
## Requirements:
##   pip install pigpio
##

import sys, re, argparse, fileinput, configparser
from time import time, sleep
from pathlib import PurePath, Path
import pigpio

sys.path.extend(['.'])
from pcc import pcc

def parse_parameter(param_str):
    if param_str is not None:
        parameter = [int(p) for p in param_str.strip('[]').split(',')[:10]]
        if len(parameter) > 0:
            return parameter + [0] * (10 - len(parameter))
    return None

class PiPcc:
    def __init__(self, hostname=None, port=8888, do_reduce=True):
        self.hostname = hostname
        self.port = port
        self.do_reduce = do_reduce
        self.out_parameter = None
        self.pi = None
        self.t0 = None

    def run(self, filenames, asm_input=False, in_parameter=None, timeout_sec=None):
        self.out_parameter = []
        if self.t0 is None:
            self.t0 = time()
        ## connect pigpiod
        pi = self.pigpiod_connect()
        if pi is None:
            return 1
        ## load or compile asm_source
        if asm_input:
            asm_filename = filenames[0]
            asm_source = self.load_asm_source(asm_filename)
        else:
            asm_filename = PurePath(filenames[-1]).stem + '.s'
            asm_source = self.compile_c_sources(filenames)
        if asm_source is None:
            return 1
        ## upload and run asm_source
        self.log_message('uploading %s to pigpiod' % asm_filename)
        asm_sid = pi.store_script(asm_source.encode('utf-8'))
        try:
            self.log_message('%s: executing with sid %d' % (asm_filename, asm_sid))
            t1 = time()
            run_result = pi.run_script(asm_sid, in_parameter)
            try:
                if run_result != 0:
                    print('*** %s: run_script() failed with error %d' % (asm_filename, run_result), file=sys.stderr)
                    return 1
                while True:
                    status, p = pi.script_status(asm_sid)
                    if status == pigpio.PI_SCRIPT_HALTED:
                        break
                    if timeout_sec is not None and time() - t1 > timeout_sec:
                        self.log_message('%s: script timed out, stopping...' % asm_filename)
                        break
                    sleep(0.01)
                status, p = pi.script_status(asm_sid)
                if status != pigpio.PI_SCRIPT_HALTED:
                    self.log_message('%s: not terminated (status: %d), stopping...' % (asm_filename, status))
                else:
                    self.log_message('%s: done, output parameter: [%s]' % (asm_filename, ', '.join([str(q) for q in p])))
                    self.out_parameter = list(p)
            finally:
                pi.stop_script(asm_sid)
        finally:
            pi.delete_script(asm_sid)
        return 0

    def run_testsuite(self, ts_filename):
        config = configparser.ConfigParser()
        config.read(ts_filename)
        for section_name in config.sections():
            section = config[section_name]
            if 'c_file' not in section:
                raise Exception('Missing config parameter "c_file" in section [%s]' % section_name)
            c_file = section.get('c_file')
            c_filepath = str(Path(ts_filename).with_name(c_file))
            param_in = parse_parameter(section.get('param_in', None))
            param_out = parse_parameter(section.get('param_out', None))
            timeout_sec = section.getint('timeout_sec', None)
            if self.run([c_filepath], in_parameter=param_in, timeout_sec=timeout_sec) != 0:
                return 1
            elif param_out is not None and param_out != self.out_parameter:
                print('*** error: unexpected output parameter, expected %s' % param_out, file=sys.stderr)
                return 1
        return 0

    ## private methods

    P_ASM_COMMENT = re.compile(r';.*')

    def log_message(self, message):
        print('%-4.3f %s' % (time()-self.t0, message), file=sys.stderr)

    def pigpiod_connect(self):
        if self.pi is None:
            if self.hostname is None:
                self.pi = pigpio.pi()
            else:
                self.pi = pigpio.pi(self.hostname, self.port)
            if not self.pi.connected:
                return None
            self.log_message('pigpiod connected')
        return self.pi

    def load_asm_source(self, asm_filename):
        if not Path(asm_filename).is_file():
            self.log_message('%s: error: file not found' % asm_filename)
            return None
        self.log_message('loading %s' % asm_filename)
        asm_lines = []
        for line in fileinput.input(asm_filename):
            asm_lines.append(self.P_ASM_COMMENT.sub('', line))
        return ''.join(asm_lines)

    def compile_c_sources(self, c_filenames):
        self.log_message('compiling %s' % ' '.join(c_filenames))
        cc = pcc(c_filenames, do_reduce=self.do_reduce)
        if cc is None:
            return None
        self.log_message('VM variables used: %d/150, tags: %d/50' % (cc.var_count, cc.tag_count))
        return cc.encode_asm()

def main():
    parser = argparse.ArgumentParser(description='pipcc - PIGS C compiler and runner')
    parser.add_argument('filenames', metavar='FILE', nargs='+', help='filenames to parse')
    parser.add_argument('-t', dest='timeout', help='script timeout in seconds')
    parser.add_argument('-p', dest='parameter', help='script input parameter, comma-separated list of int')
    parser.add_argument('-s', dest='testsuite', action='store_true', help='execute testsuite FILE')
    parser.add_argument('-i', dest='hostname', metavar='HOSTNAME', help='hostname or IP address of pigpiod')
    parser.add_argument('-o', dest='port', metavar='PORT', default=8888, help='port number of pigpiod (default: 8888)')
    parser.add_argument('-a', dest='assembler', action='store_true', help='treat input as assembly language file')
    parser.add_argument('-n', dest='no_reduce', action='store_true', help='do not reduce compiled asm code')
    args = parser.parse_args()

    pipcc = PiPcc(hostname=args.hostname, port=args.port, do_reduce=not args.no_reduce)
    try:
        if args.testsuite:
            result = pipcc.run_testsuite(args.filenames[0])
        else:
            result = pipcc.run(
                args.filenames,
                asm_input = args.assembler,
                in_parameter = parse_parameter(args.parameter),
                timeout_sec = args.timeout)
    except KeyboardInterrupt:
        print('\nAborted by CTRL+C', file=sys.stderr)
        result = 1
    return result

if __name__ == '__main__':
    sys.exit(main())
