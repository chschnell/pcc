# pcc - C compiler for pigpio's PIGS VM

A tiny C compiler for [pigpio](https://abyz.me.uk/rpi/pigpio/)'s PIGS VM written in pure Python3.

## Requirements

Requires Python package **[pycparser](https://github.com/eliben/pycparser)**:

    pip install pycparser

## Usage

### pcc.py

Compiler command line arguments:

    > python pcc.py -h
    usage: pcc.py [-h] [-o FILE] [-c] [-n] [-v] [-d] C_FILE [C_FILE ...]

    pcc - PIGS C compiler

    positional arguments:
      C_FILE      filenames to parse

    optional arguments:
      -h, --help  show this help message and exit
      -o FILE     place the output into FILE ("-" for STDOUT)
      -c          add comments to asm output
      -n          do not reduce asm output
      -d          add debug output to error messages

Specify one or more `*.c` input files on the command line. The output filename defaults to the last `*.c` filename with extension `*.s` in the current working directory. Use command line argument `-o-` to write output to STDOUT.

Input files are parsed separately and merged into a single compilation unit before compiling the assembly output, symbols declared in one input file are thus visible to subsequent input files. Header file `vm_api.h` is implicitly included (parsed first before any of the given input files) unless it is explicitly stated as an input file.

Examples:

    # compile foo.c into foo.s
    python pcc.py foo.c

    # compile foo.c to STDOUT and add comments to the assembly output
    python pcc.py -c -o- foo.c

### pipcc.py

Tool to compile, upload and execute a C program into a local or remote pigpiod VM. Command line arguments:

    > python pipcc.py -h
    usage: pipcc.py [-h] [-t TIMEOUT] [-p PARAMETER] [-s] [-i HOSTNAME] [-o PORT] [-a] [-v] FILE [FILE ...]

    pipcc - PIGS C compiler and runner

    positional arguments:
      FILE          filenames to parse

    optional arguments:
      -h, --help    show this help message and exit
      -t TIMEOUT    script timeout in seconds
      -p PARAMETER  script input parameter, comma-separated list of int
      -s            execute testsuite FILE
      -i HOSTNAME   hostname or IP address of pigpiod
      -o PORT       port number of pigpiod (default: 8888)
      -a            treat input as assembly language file
      -n            do not reduce compiled asm code

This tool first uses `pcc.py` to compile one or more `*.c` input files and then uses pigpio's Python interface to upload and run the compiled assembly code on a pigpiod instance. If no pigpio hostname is specified the local pigpiod instance is connected. If a TIMEOUT value is specified the program is stopped in case it does not `HALT` by itself within this limit.

To execute the test suite on a Raspberry Pi:

    python pipcc.py -s tests/pcc_tests.conf

## Supported C language subset

### Operators

Supported C99 operators:
 
- 11 assignment ops: `=`, `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=`, `>>=`
- 13 arithmetic ops: `+`, `-`, `*`, `/`, `%`, `&`, `|`, `^`, `<<`, `>>`, `~`, `-a`, `+a`
- 4 increment/decrement ops: `a++`, `a--`, `++a`, `--a`
- 3 logical ops: `&&`, `||`, `!`
- 6 comparison ops: `==`, `!=`, `<`, `>`, `<=`, `>=`

Unsupported C99 operators:

- 5 member access ops: `a[b]`, `*a`, `&a`, `a->b`, `a.b`
- 6 other ops: `a(...)`, `a, b`, `(type) a`, `? :`, `sizeof`, `_Alignof (since C11)`

### Statements

Supported C99 statements:

- `if`, `else`, `for`, `while`, `do`, `break`, `continue` and `return`
- compound `{ ... }` and expression statements

Unsupported C99 statements:

- `switch`, `case`, `label` and `goto`

### Declarations

Supported C99 declarations:

- type qualifiers `enum`, `int` and `void`
- function declarations

Only `int` variables and function prototypes with zero or more `int` arguments and `void` or `int` return type are supported.

Not supported:

- pointer and array declarators
- type qualifiers `struct` and `union`
- storage-class specifiers `typedef`, `auto`, `register` and `static` (`extern` is reserved for VM API symbols)
- type qualifiers `const`, `volatile` and `restrict`
- function specifier `inline`
- alignment specifiers

### Literal integer constants

The C compiler supports decimal, octal or hexadecimal notation (e.g. `123`, `0775` and `0xff`, respectively) for literal integer constants, C23's binary notation (`0b0101`) is not supported.

## VM interconnection

### VM API functions

VM API functions are special assembler commands like [`READ`](https://abyz.me.uk/rpi/pigpio/pigs.html#R/READ) or [`WRITE`](https://abyz.me.uk/rpi/pigpio/pigs.html#W/WRITE) and many others. Their equivalent C function names (in this case [`gpioRead()`](https://abyz.me.uk/rpi/pigpio/cif.html#gpioRead) and [`gpioWrite()`](https://abyz.me.uk/rpi/pigpio/cif.html#gpioWrite), respectively) are known to the compiler, and the C function prototypes are made known to the compiler in header file `vm_api.h`. This header is always implicitly included and also serves to document the VM API.

### VM Variables

Each global or local C variable is assigned to a unique VM variable `vX` (function arguments are treated like local variables and internally known to the caller). The first 4 variables are reserved by the compiler for internal use, leaving 146 variables for the program.

* `v0` is reserved by the compiler as a helper register to store interim results, and
* `v1`, `v2` and `v3` are reserved to store non-trivial VM API function arguments (meaning compound expressions as opposed to literal values, variable or parameter names).

### VM Parameters

VM parameters `p0`, `p1`, ..., `p9` are simply mapped into the global scope by name.

You can declare your own extended parameter names, use underscore `_` to separate parameter names from your extensions like in `p1_foo`, `bar_p2` or `foo_p3_bar`, for example:

    extern int foobar_p0;   // maps to parameter "p0"

## Limitations

* No C preprocessor, only simple support for C-style comments `//` and `/* ... */` (keep it simple, not all corner-cases are covered). That means anything starting with a hash (`#`) is not supported (e.g. `#include`, `#define`, ...).
* The VM's limits of 150 variables and 50 tags limit the supported number of variables and control flow statements available to the program. The number of used variables and tags is printed to STDERR after compilation, however exceeding those limits does not lead to a compiler error.
* The currently used function calling convention does not support recursion. Functions can call each other, but without direct or indirect recursion.
* No type model (only `int`).

## Proposal: VM assembly language extension

In order to efficiently map arbitrary C99 expressions to assembly code the compiler expects `F == A` to be invariantly true after any command that operates on `A` has completed, for example, any arithmetic, binary or logical operator or function calls (conceptually, currently this is implemented simply by inserting a `OR 0` before any conditional branch command, but that's a hack that is to be removed).

This is already the case for all existing arithmetic and bitwise operators like `ADD`, `MUL`, `MOD`, etc., but the following additional commands would complete the set of operators covered by C99:

|Command|Description|Definition|
|--|--|--|
|LDAF x|Load accumulator and flags with x|A=x; F=A|
|NOTL  |Logical NOT with accumulator|A=!A; F=A; A:(0\|1)|
|ANDL x|Logical AND accumulator with x|A=(A && x); F=A; A:(0\|1)|
|ORL x |Logical OR accumulator with x|A=(A \|\| x); F=A; A:(0\|1)|
|EQ x  |Test whether A == x |A=(A == x); F=A; A:(0\|1)|
|NE x  |Test whether A != x |A=(A != x); F=A; A:(0|1)|
|GT x  |Test whether A > x  |A=(A > x); F=A; A:(0\|1)|
|GE x  |Test whether A >= x |A=(A >= x); F=A; A:(0\|1)|
|LT x  |Test whether A < x  |A=(A < x); F=A; A:(0\|1)|
|LE x  |Test whether A <= x |A=(A <= x); F=A; A:(0\|1)|
|NEG   |Flip sign of accumulator|A=-A; F=A|
|BOOL  |Set A=1 if A!=0|A=(bool)A; F=A; A:(0\|1)|
|NOT   |Bitwise NOT with accumulator|A=~A; F=A|

> Note: `A:(0|1)` means that `A` is either `0` or `1`, as demanded by C99.

Currently, `NOTL`, `ANDL`, `ORL`, `EQ`, `NE`, `GT`, `GE`, `LT`, `LE` and `NEG` are implemented as CALLs to built-in functions which are dynamically added to the program by the compiler if needed. `LDAF` is (conceptually) in-lined as `LDA x; OR 0`, `NOT` is in-lined as `XOR 0xffffffff`. `BOOL` is not implemented.

This work-around suffices to streamline the implementation of the 37 C99 operators listed above but has some disadvantages, it creates complexity in the compiler and reduces the amount of TAGs available to the program, and also causes a slight amount of clutter and redundant code in the produced assembly output.

The proposed additional assembly language commands above introduce simple, isolated additions to the VM's back-end code, are fully backwards-compatible and would improve pcc considerably.
