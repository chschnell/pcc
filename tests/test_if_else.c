// test_if_else.c
// Test statements "if" and "else"

int bool(int value)
{
    if (value) {
        return true;
    }
    return false;
}

int min3(int a, int b, int c)
{
    if (a < b) {
        if (a < c) {
            return a;   // a < b && a < c
        }
        else {
            return c;   // a < b && a >= c
        }
    }
    else if (b < c) {   // a >= b && b < c
        return b;
    }
    else {              // a >= b && b >= c
        return c;
    }
}

int first_bit(int a)
{
    int i;
    for (i=0; i<32; ++i) {
        if ((1 << i) & a) {
            return i + 1;
        }
    }
    return 0;
}

void main(void)
{
    p0 = bool(0);
    p1 = bool(2);
    p2 = bool(-3);
    p3 = min3(1, 2, 3);
    p4 = min3(5, 6, 4);
    p5 = min3(9, 7, 8);
    p6 = first_bit(0);
    p7 = first_bit(32);
    p8 = first_bit(256);
    p9 = first_bit(0x80000000);
}
