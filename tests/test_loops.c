// test_loops.c
// Test C loops

int add_mul(int value, int v_add, int v_mul)
{
    return (value + v_add) * v_mul;
}

int test_loop1()
{
    int a = 0, i;
    for (i = 0; i < 10; ++i) {
        a = add_mul(a, 2, 3);
    }
    return a;
}

int test_loop2()
{
    int a = 0, i;
    for (i = 0; i < 10; ++i) {
        if (i == 7) {
            continue;
        }
        a = add_mul(a, 2, 3);
        if (8 == i) {
            break;
        }
    }
    return a;
}

int test_loop3()
{
    int a = 0, i = 0;
    while (i < 10) {
        a = add_mul(a, 2, 3);
        i++;
    }
    return a;
}

int test_loop4()
{
    int a = 0, i = 0;
    while (1) {
        if (++i == 7) {
            continue;
        }
        a = add_mul(a, 2, 3);
        if (i == 9) {
            break;
        }
    }
    return a;
}

int test_loop5()
{
    int a = 0, i = 0;
    do {
        a = add_mul(a, 2, 3);
        i++;
    } while (i < 10);
    return a;
}

int test_loop6()
{
    int a = 0, i = 0;
    do {
        if (++i == 7) {
            continue;
        }
        a = add_mul(a, 2, 3);
        if (i == 9) {
            break;
        }
    } while (i < 10);
    return a;
}

int test_loop7()
{
    int i = 0;

    while (0) {
        ++i;
    }
    if (i != 0) {
        return -1;
    }

    do {
        ++i;
    } while (0);
    if (i != 1) {
        return -2;
    }

    for (;;) {
        ++i;
        if (i == 100) {
            break;
        }
    }
    if (i != 100) {
        return -3;
    }

    int z = 0;
    for (int i=0; i<10; ++i) {
        ++z;
    }
    if (z != 10) {
        return -4;
    }

    z = 0;
    for (int j=0; j<10; ++j) {
        ++z;
    }
    if (z != 10) {
        return -5;
    }

    i = 0;
    z = 0;
    for (int j=0, k=100; j<=20; ++j, ++k) {
        i = j;
        z = k;
    }
    if ((i != 20) || (z != 120)) {
        return -7;
    }

    return 1;
}

void main()
{
    p0 = test_loop1();
    p1 = test_loop2();
    p2 = test_loop3();
    p3 = test_loop4();
    p4 = test_loop5();
    p5 = test_loop6();
    p6 = test_loop7();
}
