// test_other.c

// [-1, 2, 1, 32770, 0, 0, 1, 1, 1, 1]

int test_orb(int a, int);

void main(void)
{
    p0 = PI_INIT_FAILED;    // -1
    p1 = -1;
    p1 = 1;
    ++p1;

    p2++;
    p3 = (1 << p2) | 0x8000;

    int b=0, d=2, e=3;

    p4 = b && d;
    p5 = d && b;
    p6 = d && e;
    p7 = test_orb(b, d);
    p8 = test_orb(d, b);
    p9 = test_orb(d, e);
}

int test_orb(int a, int b)
{
    return a || b;
}
