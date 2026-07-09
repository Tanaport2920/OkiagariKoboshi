import argparse
from pathlib import Path

import torch


def find_actor_layers(state_dict, expected):
    candidates = []

    for k, v in state_dict.items():
        if not k.endswith(".weight"):
            continue
        if not hasattr(v, "ndim") or v.ndim != 2:
            continue
        if "critic" in k.lower():
            continue
        if "actor" not in k.lower():
            continue

        out_dim, in_dim = v.shape
        candidates.append((k, in_dim, out_dim))

    layers = []
    used = set()

    for in_dim, out_dim in expected:
        matched = None
        for k, kin, kout in candidates:
            if k in used:
                continue
            if kin == in_dim and kout == out_dim:
                matched = k
                break
        if matched is None:
            raise RuntimeError(
                f"Could not find actor layer {in_dim}->{out_dim}. "
                f"candidates={candidates}"
            )
        used.add(matched)
        layers.append(matched)

    return layers


def array_to_c(name, tensor):
    flat = tensor.detach().cpu().float().contiguous().view(-1).numpy()
    values = ", ".join(f"{x:.9g}f" for x in flat)
    return f"static const float {name}[{len(flat)}] = {{\n    {values}\n}};\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--input-dim", type=int, default=13)
    parser.add_argument("--h1-dim", type=int, default=64)
    parser.add_argument("--h2-dim", type=int, default=64)
    parser.add_argument("--output-dim", type=int, default=2)
    args = parser.parse_args()

    ckpt = torch.load(args.checkpoint, map_location="cpu")

    if "model_state_dict" in ckpt:
        sd = ckpt["model_state_dict"]
    elif "state_dict" in ckpt:
        sd = ckpt["state_dict"]
    else:
        sd = ckpt

    print("state_dict keys:")
    for k in sd.keys():
        if "actor" in k.lower():
            shape = tuple(sd[k].shape) if hasattr(sd[k], "shape") else ""
            print(" ", k, shape)

    expected = [
        (args.input_dim, args.h1_dim),
        (args.h1_dim, args.h2_dim),
        (args.h2_dim, args.output_dim),
    ]
    w_keys = find_actor_layers(sd, expected)
    b_keys = [k.replace(".weight", ".bias") for k in w_keys]

    for k in b_keys:
        if k not in sd:
            raise RuntimeError(f"Missing bias: {k}")

    out = []
    out.append("#pragma once\n")
    out.append("// Auto-generated from RSL-RL Actor checkpoint\n")
    out.append(f"#define POLICY_IN_DIM {args.input_dim}\n")
    out.append(f"#define POLICY_H1_DIM {args.h1_dim}\n")
    out.append(f"#define POLICY_H2_DIM {args.h2_dim}\n")
    out.append(f"#define POLICY_OUT_DIM {args.output_dim}\n\n")

    out.append(array_to_c("W1", sd[w_keys[0]]))
    out.append(array_to_c("B1", sd[b_keys[0]]))
    out.append(array_to_c("W2", sd[w_keys[1]]))
    out.append(array_to_c("B2", sd[b_keys[1]]))
    out.append(array_to_c("W3", sd[w_keys[2]]))
    out.append(array_to_c("B3", sd[b_keys[2]]))

    Path(args.out).write_text("\n".join(out))
    print(f"actor layers: {w_keys}")
    print(f"wrote: {args.out}")


if __name__ == "__main__":
    main()
