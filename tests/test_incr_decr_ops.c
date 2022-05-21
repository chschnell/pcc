// test_incr_decr_ops.c
// Test increment and decrement operators

int test_incr_decr_ops(void)
{
    int a = 10;

    if (a++ != 10) {
        return -1;
    }

    if (a != 11) {
        return -2;
    }

    if (++a != 12) {
        return -3;
    }

    if (a != 12) {
        return -4;
    }

    if (a-- != 12) {
        return -5;
    }

    if (a != 11) {
        return -6;
    }

    if (--a != 10) {
        return -7;
    }

    if (a != 10) {
        return -8;
    }

    return 1;
}

void main()
{
    p0 = test_incr_decr_ops();
}
