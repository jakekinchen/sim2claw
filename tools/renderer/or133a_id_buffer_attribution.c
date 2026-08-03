#include <math.h>
#include <stddef.h>
#include <stdint.h>

/*
 * OR133A read-only instrumentation sibling of or79_triangle_rasterizer.c.
 * The raster loop and depth comparison intentionally remain byte-for-byte
 * equivalent in behavior.  The only added side effect is recording the
 * caller-provided group id whenever the winning fragment updates the RGB and
 * depth buffers.
 */
int rasterize_triangles_with_ids(
    uint8_t *frame,
    double *zbuffer,
    uint16_t *idbuffer,
    int width,
    int height,
    const double *pixels,
    const double *depths,
    const uint8_t *colors,
    const uint16_t *group_ids,
    size_t triangle_count,
    uint64_t *depth_updates,
    uint64_t *occluded_fragments
) {
    uint64_t updates_total = 0;
    uint64_t occluded_total = 0;
    for (size_t triangle = 0; triangle < triangle_count; ++triangle) {
        const double *p = pixels + triangle * 6;
        const double *d = depths + triangle * 3;
        const uint8_t *color = colors + triangle * 3;
        if (d[0] <= 1e-4 || d[1] <= 1e-4 || d[2] <= 1e-4) {
            continue;
        }
        int finite = 1;
        for (int value = 0; value < 6; ++value) {
            finite = finite && isfinite(p[value]);
        }
        if (!finite) {
            continue;
        }
        double minimum_x = fmin(p[0], fmin(p[2], p[4]));
        double minimum_y = fmin(p[1], fmin(p[3], p[5]));
        double maximum_x = fmax(p[0], fmax(p[2], p[4]));
        double maximum_y = fmax(p[1], fmax(p[3], p[5]));
        int x0 = (int)floor(minimum_x);
        int y0 = (int)floor(minimum_y);
        int x1 = (int)ceil(maximum_x);
        int y1 = (int)ceil(maximum_y);
        if (x0 < 0) x0 = 0;
        if (y0 < 0) y0 = 0;
        if (x1 >= width) x1 = width - 1;
        if (y1 >= height) y1 = height - 1;
        if (x1 < x0 || y1 < y0) {
            continue;
        }
        double denominator =
            (p[3] - p[5]) * (p[0] - p[4]) +
            (p[4] - p[2]) * (p[1] - p[5]);
        if (fabs(denominator) <= 1e-12) {
            continue;
        }
        uint64_t fragments = 0;
        uint64_t updates = 0;
        for (int y_index = y0; y_index <= y1; ++y_index) {
            double y = (double)y_index + 0.5;
            for (int x_index = x0; x_index <= x1; ++x_index) {
                double x = (double)x_index + 0.5;
                double w0 =
                    ((p[3] - p[5]) * (x - p[4]) +
                     (p[4] - p[2]) * (y - p[5])) /
                    denominator;
                double w1 =
                    ((p[5] - p[1]) * (x - p[4]) +
                     (p[0] - p[4]) * (y - p[5])) /
                    denominator;
                double w2 = 1.0 - w0 - w1;
                if (w0 < -1e-9 || w1 < -1e-9 || w2 < -1e-9) {
                    continue;
                }
                ++fragments;
                double inverse_depth = w0 / d[0] + w1 / d[1] + w2 / d[2];
                double depth = inverse_depth > 0.0 ? 1.0 / inverse_depth : INFINITY;
                size_t pixel_index = (size_t)y_index * (size_t)width + (size_t)x_index;
                if (depth < zbuffer[pixel_index]) {
                    zbuffer[pixel_index] = depth;
                    idbuffer[pixel_index] = group_ids[triangle];
                    size_t frame_index = pixel_index * 3;
                    frame[frame_index] = color[0];
                    frame[frame_index + 1] = color[1];
                    frame[frame_index + 2] = color[2];
                    ++updates;
                }
            }
        }
        updates_total += updates;
        occluded_total += fragments - updates;
    }
    *depth_updates = updates_total;
    *occluded_fragments = occluded_total;
    return 0;
}
