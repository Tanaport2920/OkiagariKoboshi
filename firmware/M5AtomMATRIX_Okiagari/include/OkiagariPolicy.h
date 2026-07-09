#pragma once

#include <stddef.h>

namespace OkiagariPolicy {

constexpr size_t kObservationSize = 13;
constexpr size_t kActionSize = 2;

// Fill action with normalized servo targets in [-1, 1].
// Return true when a real policy was evaluated.  The placeholder returns false
// so main.cpp can keep the robot in a safe zero-target state.
bool run(const float observation[kObservationSize],
         float action[kActionSize]);

}  // namespace OkiagariPolicy
