#include "engine.hpp"
#include <iostream>

void Engine::step() {
    for (auto& p : positions_) {
        p = p + Vec2{1, 0};
        renderer_.draw(p);
    }
}
