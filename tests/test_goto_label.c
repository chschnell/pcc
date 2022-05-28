// test_goto_label.c
// Test statements "label" and "goto"

void goto_label_test1(void)
{
    int i = 0;

    p0 = 1;
    goto main_start;
    p0 = -1;
    goto done;

    {
main_start:
        p1 = 2;

loop_begin:
        if (i == 3)
            goto loop_end;
        ++i;
        goto loop_begin;

    }
loop_end:
    p2 = i;

done:
    return;
}

void goto_label_test2(void)
{
    p3 = 4;
    goto done;
    return;

done:
    p4 = 5;
}

void main(void)
{
    goto_label_test1();
    goto_label_test2();
}
