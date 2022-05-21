// test_comparison_ops.c
// Test comparison operators

int test_comparison_ops1(void)
{
    if (1 == 1) {
    }
    else {
        return -1;
    }

    if (2 != 2) {
        return -2;
    }

    if (3 < 3) {
        return -3;
    }
    if (3 < 4) {
    }
    else {
        return -4;
    }
    if (4 < 3) {
        return -5;
    }

    if (4 > 4) {
        return -6;
    }
    if (5 > 4) {
    }
    else {
        return -7;
    }
    if (4 > 5) {
        return -8;
    }

    if (6 <= 5) {
        return -9;
    }
    if (6 <= 6) {
    }
    else {
        return -10;
    }
    if (5 <= 6) {
    }
    else {
        return -11;
    }

    if (7 >= 8) {
        return -12;
    }
    if (8 >= 8) {
    }
    else {
        return -13;
    }
    if (8 >= 7) {
    }
    else {
        return -14;
    }

    return 1;
}

int test_comparison_ops2(void)
{
    int a, b;

    a = 1;
    if (a == 1) {
    }
    else {
        return -1;
    }

    b = 1;
    if (1 == b) {
    }
    else {
        return -2;
    }

    if (a == b) {
    }
    else {
        return -3;
    }

    a = 3;
    if (a < 3) {
        return -4;
    }
    if (a < 4) {
    }
    else {
        return -5;
    }
    a = 4;
    if (a < 3) {
        return -5;
    }

    a = 3; b = 3;
    if (a < b) {
        return -6;
    }
    b = 4;
    if (a < b) {
    }
    else {
        return -7;
    }
    a = 4; b = 3;
    if (a < b) {
        return -8;
    }

    return 2;
}

void main()
{
    p0 = test_comparison_ops1();
    p1 = test_comparison_ops2();
}
