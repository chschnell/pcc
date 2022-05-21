// test_assignment.c
// Test assignment operators

int test_assignment_ops1(void)
{
    int a;

    a = 3;
    if (a != 3) {
        return -1;
    }

    a = 3;
    a += 5;
    if (a != 8) {
        return -2;
    }

    a = 5;
    a -= 3;
    if (a != 2) {
        return -3;
    }

    a = 3;
    a *= 5;
    if (a != 15) {
        return -4;
    }

    a = 21;
    a /= 7;
    if (a != 3) {
        return -5;
    }

    a = 43;
    a %= 10;
    if (a != 3) {
        return -6;
    }

    a = 0x90;
    a &= 0x10;
    if (a != 0x10) {
        return -7;
    }

    a = 0x40;
    a |= 0x08;
    if (a != 0x48) {
        return -8;
    }

    a = 0xff;
    a ^= 0x55;          // 0b01010101
    if (a != 0xaa) {    // 0b10101010
        return -9;
    }

    a = 0x20;
    a <<= 2;
    if (a != 0x80) {
        return -10;
    }

    a = 0x8000;
    a >>= 3;
    if (a != 0x1000) {
        return -11;
    }

    return 1;
}

int test_assignment_ops2(void)
{
    int a, b;

    a = 3;
    if (a != 3) {
        return -1;
    }

    b = 8;
    a = 3;
    a += 5;
    if (a != b) {
        return -2;
    }

    b = 2;
    a = 5;
    a -= 3;
    if (a != b) {
        return -3;
    }

    b = 15;
    a = 3;
    a *= 5;
    if (a != b) {
        return -4;
    }

    b = 3;
    a = 21;
    a /= 7;
    if (a != b) {
        return -5;
    }

    b = 3;
    a = 43;
    a %= 10;
    if (a != b) {
        return -6;
    }

    b = 0x10;
    a = 0x90;
    a &= 0x10;
    if (a != b) {
        return -7;
    }

    b = 0x48;
    a = 0x40;
    a |= 0x08;
    if (a != b) {
        return -8;
    }

    b = 0xaa;           // 0b10101010
    a = 0xff;
    a ^= 0x55;          // 0b01010101
    if (a != b) {
        return -9;
    }

    b = 0x80;
    a = 0x20;
    a <<= 2;
    if (a != b) {
        return -10;
    }

    b = 0x1000;
    a = 0x8000;
    a >>= 3;
    if (a != b) {
        return -11;
    }

    return 2;
}

void main()
{
    p0 = test_assignment_ops1();
    p1 = test_assignment_ops2();
}
