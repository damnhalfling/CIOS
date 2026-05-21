// CIOS Identity Disc Shader
// The central ring that represents the CIOS runtime state

struct DiscUniforms {
    time: f32,
    rotation: f32,
    scale: f32,
    state: u32, // 0=idle, 1=listening, 2=local, 3=cloud, 4=exec, 5=error
    primary_color: vec4<f32>,
    resolution: vec2<f32>,
    _padding: vec2<f32>,
}

@group(0) @binding(0) var<uniform> u: DiscUniforms;

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
}

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var positions = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(-1.0, -1.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(-1.0, 1.0),
    );

    var out: VertexOutput;
    out.position = vec4<f32>(positions[vertex_index], 0.0, 1.0);
    out.uv = positions[vertex_index];
    return out;
}

// Signed distance to a ring
fn sd_ring(p: vec2<f32>, radius: f32, thickness: f32) -> f32 {
    return abs(length(p) - radius) - thickness;
}

// Segmented ring (like TRON disc)
fn segmented_ring(p: vec2<f32>, radius: f32, thickness: f32, segments: f32, rotation: f32) -> f32 {
    let angle = atan2(p.y, p.x) + rotation;
    let seg = fract(angle / (6.283185 / segments));
    let gap = smoothstep(0.0, 0.05, seg) * smoothstep(1.0, 0.95, seg);
    let ring = sd_ring(p, radius, thickness);
    return mix(1.0, gap, step(ring, 0.0)) * step(ring, 0.002);
}

// Concentric code lines (listening state)
fn code_lines(p: vec2<f32>, time: f32, rotation: f32) -> f32 {
    var intensity = 0.0;
    let dist = length(p);
    let angle = atan2(p.y, p.x) + rotation;

    for (var i = 0; i < 8; i++) {
        let fi = f32(i);
        let r = 0.2 + fi * 0.05;
        let ring_dist = abs(dist - r * u.scale);

        // Animated segments
        let seg_angle = angle + time * (1.0 + fi * 0.5);
        let seg = step(0.3, fract(seg_angle * (3.0 + fi) / 6.283185));

        let line = smoothstep(0.003, 0.0, ring_dist) * seg;
        intensity += line * (1.0 - fi * 0.1);
    }

    return intensity;
}

// Glow effect
fn glow(dist: f32, intensity: f32, radius: f32) -> f32 {
    return intensity / (1.0 + pow(dist / radius, 2.0));
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let uv = in.uv;
    let aspect = u.resolution.x / u.resolution.y;
    var p = uv;
    p.x *= aspect;

    let time = u.time;
    let color = u.primary_color.rgb;

    var intensity = 0.0;

    // Main outer ring
    let outer_ring = segmented_ring(p, 0.35 * u.scale, 0.008, 32.0, u.rotation);
    intensity += outer_ring;

    // Inner ring
    let inner_ring = segmented_ring(p, 0.25 * u.scale, 0.005, 16.0, -u.rotation * 1.5);
    intensity += inner_ring * 0.8;

    // Core dot
    let core_dist = length(p);
    let core = smoothstep(0.02 * u.scale, 0.0, core_dist);
    intensity += core * 0.5;

    // State-specific effects
    if u.state == 1u { // Listening - expanding code lines
        intensity += code_lines(p, time, u.rotation) * 0.6;
    }

    if u.state == 3u { // Cloud - outer energy ring
        let energy_ring = sd_ring(p, 0.45 * u.scale, 0.003);
        let energy = smoothstep(0.005, 0.0, abs(energy_ring));
        let pulse = (sin(time * 5.0) * 0.5 + 0.5);
        intensity += energy * pulse;
    }

    if u.state == 5u { // Error - fragmentation
        let frag = fract(sin(dot(floor(p * 20.0), vec2<f32>(12.9898, 78.233))) * 43758.5453);
        let jitter = step(0.7, frag) * step(0.3, fract(time * 10.0 + frag));
        intensity *= (1.0 - jitter * 0.5);
    }

    // Outer glow
    let glow_amount = glow(core_dist, 0.1, 0.4 * u.scale);

    // Final composition
    let final_color = color * (intensity + glow_amount);

    // Alpha: transparent where no disc
    let alpha = clamp(intensity + glow_amount * 0.5, 0.0, 1.0);

    return vec4<f32>(final_color, alpha);
}
