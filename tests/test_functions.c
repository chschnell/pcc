// test_functions.c
// Test user defined functions

int test_forward();

int test_local_decl(int a)
{
    int test_normal(int a);
    return 1 + test_normal(a);
}

int test_normal(int a)
{
    return a + 1;
}

int test_anon_arg(int a, int)
{
    return a + 1;
}

int test_unused_1(void)
{
    int test_unused_2();
    int test_unused_3(int a, int b);
    return (test_unused_2() && test_unused_3(4, 3)) >= 0;
}

int test_unused_2(void)
{
    int test_unused_3(int a, int b);
    return 1 + test_unused_3(3, 4);
}

int test_unused_3(int a, int b)
{
    return a || b;
}

int test_add(int a, int b)
{
    return a + b;
}

void main(void)
{
    p0 = test_forward();
    p1 = test_normal(1);
    p2 = test_anon_arg(2, 3);
    p3 = test_local_decl(2);
    p4 = test_add(2, 3) + test_add(5, 10);
}

int test_forward(void)
{
    return 1;
}
