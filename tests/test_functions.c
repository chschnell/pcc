// test_functions.c
// Test user defined functions

int test_forward();

int test_normal(int a)
{
    return a + 1;
}

int test_anon_arg(int a, int)
{
    return a + 1;
}

void main(void)
{
    p0 = test_forward();
    p1 = test_normal(1);
    p2 = test_anon_arg(2, 3);
}

int test_forward(void)
{
    return 1;
}
