#include "OkiagariPolicy.h"

#include <Arduino.h>
#include <math.h>

#if __has_include("policy_weights.h")
// Arduino's binary.h defines B1 as a macro, which collides with generated
// policy bias arrays named B1.
#ifdef B1
#undef B1
#endif
#include "policy_weights.h"
#define OKIAGARI_HAS_POLICY_WEIGHTS 1
#else
#define OKIAGARI_HAS_POLICY_WEIGHTS 0
#endif

namespace OkiagariPolicy {

#if OKIAGARI_HAS_POLICY_WEIGHTS
namespace {

bool printedPolicyInfo = false;

float relu(float x) {
    return x > 0.0f ? x : 0.0f;
}

void denseRelu(const float* input, const float* weights, const float* bias,
               int inDim, int outDim, float* output) {
    for (int row = 0; row < outDim; ++row) {
        float sum = bias[row];
        const float* w = weights + row * inDim;
        for (int col = 0; col < inDim; ++col) {
            sum += w[col] * input[col];
        }
        output[row] = relu(sum);
    }
}

void denseLinear(const float* input, const float* weights, const float* bias,
                 int inDim, int outDim, float* output) {
    for (int row = 0; row < outDim; ++row) {
        float sum = bias[row];
        const float* w = weights + row * inDim;
        for (int col = 0; col < inDim; ++col) {
            sum += w[col] * input[col];
        }
        output[row] = sum;
    }
}

}  // namespace
#endif

bool run(const float observation[kObservationSize],
         float action[kActionSize]) {
#if OKIAGARI_HAS_POLICY_WEIGHTS
    if (!printedPolicyInfo) {
        printedPolicyInfo = true;
        Serial.printf(
            "[policy] weights found input=%d h1=%d h2=%d output=%d firmware_obs=%u\n",
            POLICY_IN_DIM, POLICY_H1_DIM, POLICY_H2_DIM, POLICY_OUT_DIM,
            static_cast<unsigned>(kObservationSize));
    }

    if (POLICY_OUT_DIM != static_cast<int>(kActionSize) ||
        POLICY_IN_DIM > static_cast<int>(kObservationSize)) {
        action[0] = 0.0f;
        action[1] = 0.0f;
        Serial.println("[policy] dimension mismatch; returning zero action");
        return false;
    }

    float h1[POLICY_H1_DIM];
    float h2[POLICY_H2_DIM];
    denseRelu(observation, W1, B1, POLICY_IN_DIM, POLICY_H1_DIM, h1);
    denseRelu(h1, W2, B2, POLICY_H1_DIM, POLICY_H2_DIM, h2);
    denseLinear(h2, W3, B3, POLICY_H2_DIM, POLICY_OUT_DIM, action);

    for (size_t i = 0; i < kActionSize; ++i) {
        if (!isfinite(action[i])) action[i] = 0.0f;
    }
    return true;
#else
    (void)observation;
    action[0] = 0.0f;
    action[1] = 0.0f;

    return false;
#endif
}

}  // namespace OkiagariPolicy
