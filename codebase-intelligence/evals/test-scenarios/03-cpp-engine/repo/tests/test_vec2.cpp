#include "vec2.hpp"
#include <cassert>

int main() {
    Vec2 a{1, 2}, b{3, 4};
    assert((a + b).x == 4);
    return 0;
}
