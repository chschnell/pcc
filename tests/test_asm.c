// test_asm.c
// Test inline assembly using asm()

int test_asm_loop()
{
    int j=10;
    int i=0;
    asm("Tag", "loop_start");
    if (i >= 10) {
        asm("jmp", "loop_end");
    }
    ++j;
    ++i;
    asm("jmp", "loop_start");
    asm("Tag", "loop_end");
    return j;
}

int fibbonacci(int n)
{
    int r1, r2;
    if (n == 0) {
        return 0;
    }
    else if (n == 1) {
        return 1;
    }
    else {
        asm("push", n);         // save our argument n on stack
        r1 = fibbonacci(n-1);
        asm("pop", n);          // restore our argument n from stack
        asm("push", r1);        // save fibbonacci(n-1) on stack

        asm("push", n);         // save our argument n on stack
        r2 = fibbonacci(n-2);
        asm("pop", n);          // restore our argument n from stack
        asm("pop", r1);         // restore fibbonacci(n-1) from stack into r1

        return r1 + r2;         // return fibbonacci(n-1) + fibbonacci(n-2)
    }
}

void main(void)
{
    p0 = test_asm_loop();
    p1 = fibbonacci(6);
    p2 = fibbonacci(7);
    p3 = fibbonacci(8);
    p4 = fibbonacci(9);
    p5 = fibbonacci(10);
    p6 = fibbonacci(11);
    p7 = fibbonacci(12);
    p8 = fibbonacci(13);
    p9 = fibbonacci(14);
}
