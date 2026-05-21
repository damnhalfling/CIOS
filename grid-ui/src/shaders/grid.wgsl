// CIOS Grid Background Shader
// Infinite coordinate plane with pulsing neon data lines

struct Uniforms {
    time: f32,
    resolution: vec2<f32>,
    pulse_phase: f32,
    primary_color: vec4<f32>,
}

@group(0) @binding(0) var<uniform> u: Uniforms;

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
}

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    // Full-screen quad
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
    out.uv = positions[vertex_index] * 0.5 + 0.5;
    return out;
}

// Perspective grid with vanishing point
fn grid_intensity(uv: vec2<f32>, time: f32) -> f32 {
    // Transform to perspective view
    let perspective_y = uv.y * 2.0 - 1.0;
    let depth = 1.0 / (abs(perspective_y) + 0.1);

    // Grid lines
    let grid_x = uv.x * 40.0 * depth;
    let grid_z = time * 2.0 + depth * 20.0;

    let line_x = smoothstep(0.0, 0.05, abs(fract(grid_x) - 0.5));
    let line_z = smoothstep(0.0, 0.05, abs(fract(grid_z) - 0.5));

    let grid = (1.0 - line_x) + (1.0 - line_z);

    // Fade with distance
    let fade = exp(-abs(perspective_y) * 1.5);

    return grid * fade * 0.3;
}

// Horizontal data flow lines
fn data_lines(uv: vec2<f32>, time: f32) -> f32 {
    var intensity = 0.0;

    // Multiple horizontal lines at different speeds
    for (var i = 0; i < 5; i++) {
        let fi = f32(i);
        let y_pos = fract(fi * 0.2 + time * (0.1 + fi * 0.05));
        let dist = abs(uv.y - y_pos);
        let line = smoothstep(0.003, 0.0, dist);

        // Animated segments
        let seg = step(0.5, fract(uv.x * 10.0 + time * (1.0 + fi) + fi * 3.14));
        intensity += line * seg * 0.4;
    }

    return intensity;
}

// Vertical energy pulses
fn energy_pulses(uv: vec2<f32>, time: f32, pulse: f32) -> f32 {
    var intensity = 0.0;

    for (var i = 0; i < 3; i++) {
        let fi = f32(i);
        let x_pos = fract(fi * 0.33 + 0.1);
        let dist = abs(uv.x - x_pos);
        let line = smoothstep(0.002, 0.0, dist);

        // Pulse traveling up
        let pulse_pos = fract(time * 0.3 + fi * 0.5);
        let pulse_dist = abs(uv.y - pulse_pos);
        let pulse_glow = exp(-pulse_dist * 20.0) * pulse;

        intensity += line * 0.1 + pulse_glow * line * 2.0;
    }

    return intensity;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let uv = in.uv;
    let time = u.time;

    // Deep space background: #00050d
    let bg = vec3<f32>(0.0, 0.02, 0.05);

    // Grid
    let grid = grid_intensity(uv, time);

    // Data lines
    let data = data_lines(uv, time);

    // Energy pulses
    let pulses = energy_pulses(uv, time, u.pulse_phase);

    // Combine with primary color
    let neon = u.primary_color.rgb;
    let combined = bg + neon * (grid + data + pulses);

    // Subtle vignette
    let vignette = 1.0 - length(uv - 0.5) * 0.8;

    return vec4<f32>(combined * vignette, 1.0);
}
