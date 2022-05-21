// test_arithmetic_ops.c
// Test arithmetic operators

int test_arithmetic_ops1(void)
{
    if (+3 != 3) {
        return -1;
    }

    if (-(3) != -3) {
        return -2;
    }

    if (~1 != 0xfffffffe) {
        return -3;
    }

    if (3 + 5 != 8) {
        return -4;
    }

    if (11 - 7 != 4) {
        return -5;
    }

    if (13 * 11 != 143) {
        return -6;
    }

    if (21 / 7 != 3) {
        return -7;
    }

    if (73 % 20 != 13) {
        return -8;
    }

    if ((0x8888 & 0x80) != 0x80) {
        return -9;
    }

    if ((0xc000 | 0xafe) != 0xcafe) {
        return -10;
    }

    if ((0x531 ^ 0xffff) != 0xface) {
        return -11;
    }

    if ((0x01 << 7) != 0x80) {
        return -12;
    }

    if ((0x40000000 >> 30) != 0x01) {
        return -13;
    }

    if ((0x80000000 >> 31) != -1) {
        return -14;
    }

    return 1;
}

int test_arithmetic_ops2(void)
{
    int a;

    a = +3;
    if (a != 3) {
        return -1;
    }

    a = -3;
    if (a != -3) {
        return -2;
    }

    a = ~1;
    if (a != 0xfffffffe) {
        return -3;
    }

    a = 3;
    if (a + 5 != 8) {
        return -4;
    }

    a = 11;
    if (a - 7 != 4) {
        return -5;
    }

    a = 13;
    if (a * 11 != 143) {
        return -6;
    }

    a = 21;
    if (a / 7 != 3) {
        return -7;
    }

    a = 73;
    if (a % 20 != 13) {
        return -8;
    }

    a = 0x8888;
    if ((a & 0x80) != 0x80) {
        return -9;
    }

    a = 0xc000;
    if ((a | 0xafe) != 0xcafe) {
        return -10;
    }

    a = 0x531;
    if ((a ^ 0xffff) != 0xface) {
        return -11;
    }

    a = 0x01;
    if ((a << 7) != 0x80) {
        return -12;
    }

    a = 0x40000000;
    if ((a >> 30) != 0x01) {
        return -13;
    }

    a = 0x80000000;
    if ((a >> 31) != -1) {
        return -14;
    }

    return 2;
}

int test_arithmetic_ops3(void)
{
    int b;

    b = 3;
    if (+3 != b) {
        return -1;
    }

    b = -3;
    if (-(3) != b) {
        return -2;
    }

    b = 0xfffffffe;
    if (~1 != b) {
        return -3;
    }

    b = 5;
    if (3 + b != 8) {
        return -4;
    }

    b = 7;
    if (11 - b != 4) {
        return -5;
    }

    b = 11;
    if (13 * b != 143) {
        return -6;
    }

    b = 7;
    if (21 / b != 3) {
        return -7;
    }

    b = 20;
    if (73 % b != 13) {
        return -8;
    }

    b = 0x80;
    if ((0x8888 & b) != 0x80) {
        return -9;
    }

    b = 0xafe;
    if ((0xc000 | b) != 0xcafe) {
        return -10;
    }

    b = 0xffff;
    if ((0x531 ^ b) != 0xface) {
        return -11;
    }

    b = 7;
    if ((0x01 << b) != 0x80) {
        return -12;
    }

    b = 30;
    if ((0x40000000 >> b) != 0x01) {
        return -13;
    }

    b = 31;
    if ((0x80000000 >> b) != -1) {
        return -14;
    }

    return 3;
}

void main()
{
    p0 = test_arithmetic_ops1();
    p1 = test_arithmetic_ops2();
    p2 = test_arithmetic_ops3();
}
