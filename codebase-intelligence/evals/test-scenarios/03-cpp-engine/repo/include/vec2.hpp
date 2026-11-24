#pragma once

struct Vec2 {
    float x = 0, y = 0;
    Vec2 operator+(const Vec2& o) const { return {x + o.x, y + o.y}; }
};
