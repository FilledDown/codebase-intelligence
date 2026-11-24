#pragma once
#include <vector>
#include "renderer.hpp"

class Engine {
public:
    void step();
private:
    std::vector<Vec2> positions_;
    Renderer renderer_;
};
