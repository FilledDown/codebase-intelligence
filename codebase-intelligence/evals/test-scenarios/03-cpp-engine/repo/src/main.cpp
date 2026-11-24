#include "engine.hpp"

int main() {
    Engine e;
    for (int i = 0; i < 3; ++i) e.step();
    return 0;
}
