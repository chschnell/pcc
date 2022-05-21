// test_scope.c
// Test C scope mechanics

void test_scope();

int a = 1;

void main(void)
{
    p0 = a;             // p0=1
    test_scope();
    p9 = a;             // p9=1
}

void test_scope(void)
{
    p1 = a;             // p1=1
    int a = 2;
    p2 = a;             // p2=2
    {
        p3 = a;         // p3=2
        int a = 3;
        p4 = a;         // p4=3
        {
            p5 = a;     // p5=3
            int a = 4;
            p6 = a;     // p6=4
        }
        p7 = a;         // p7=3
    }
    p8 = a;             // p8=2
}
