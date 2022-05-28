// test_goto_label.c
// Test "enum" declaration

int enum_test1()
{
    enum {
        STATE_IDLE,
        STATE_BUSY
    };
    int state = STATE_IDLE;
    return state;
}

int enum_test2()
{
    enum {
        STATE_IDLE,
        STATE_BUSY
    };
    int state = STATE_BUSY;
    return state;
}

int enum_test3()
{
    enum {
        STATE_IDLE = 100,
        STATE_BUSY
    } state = STATE_IDLE;
    return state;
}

int enum_test4()
{
    enum {
        STATE_IDLE = 100,
        STATE_BUSY
    } state = STATE_BUSY;
    return state;
}

void main(void)
{
    p0 = enum_test1();
    p1 = enum_test2();
    p2 = enum_test3();
    p3 = enum_test4();
}
