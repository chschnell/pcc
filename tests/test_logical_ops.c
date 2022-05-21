// test_incr_decr_ops.c
// Test logical operators

int test_logical_ops1(void)
{
    if (0 && 0) {
        return -1;
    }

    if (0 && 1) {
        return -2;
    }

    if (1 && 0) {
        return -3;
    }

    if (1 && 2) {
    }
    else {
        return -4;
    }

    if (0 || 0) {
        return -5;
    }

    if (0 || 1) {
    }
    else {
        return -6;
    }
    
    if (1 || 0) {
    }
    else {
        return -7;
    }

    if (1 || 2) {
    }
    else {
        return -8;
    }

    return 1;
}

int test_logical_ops2(void)
{
    int a;

    a = 0;
    if (a && 0) {
        return -1;
    }

    if (a && 1) {
        return -2;
    }

    a = 1;
    if (a && 0) {
        return -3;
    }

    if (a && 2) {
    }
    else {
        return -4;
    }

    a = 0;
    if (a || 0) {
        return -5;
    }

    if (a || 1) {
    }
    else {
        return -6;
    }
    
    a = 1;
    if (a || 0) {
    }
    else {
        return -7;
    }

    if (a || 2) {
    }
    else {
        return -8;
    }

    return 2;
}


int test_logical_ops3(void)
{
    int a, b;

    a = 0; b = 0;
    if (a && b) {
        return -1;
    }

    b = 1;
    if (a && b) {
        return -2;
    }

    a = 1; b = 0;
    if (a && b) {
        return -3;
    }

    b = 2;
    if (a && b) {
    }
    else {
        return -4;
    }

    a = 0; b = 0;
    if (a || b) {
        return -5;
    }

    b = 1;
    if (a || b) {
    }
    else {
        return -6;
    }
    
    a = 1; b = 0;
    if (a || b) {
    }
    else {
        return -7;
    }

    b = 2;
    if (a || b) {
    }
    else {
        return -8;
    }

    return 3;
}

void main()
{
    p0 = test_logical_ops1();
    p1 = test_logical_ops2();
    p2 = test_logical_ops3();
}
