/**
 * document-scanner.js — ID Card Scanner (Improved Detection)
 *
 * Detection pipeline:
 *   1. Brightness + Laplacian-variance quality gates
 *   2. Grayscale → Gaussian blur → Sobel X/Y components
 *   3. Axis-projection analysis (sum |Sobel_Y| per row → horizontal card edges;
 *      sum |Sobel_X| per col → vertical card edges)
 *   4. Peak-pair finding constrained to guide zone + margin
 *   5. Candidate rectangle scoring: aspect-ratio × guide-overlap × area × edge-strength
 *   6. Stability tracking: same corners ±4 % for 3+ frames
 *   7. Confidence colour: green (stable + high) / amber (detecting) / red (low)
 *
 * Modes:  'scan'  → Phase 1 detect → Phase 2 corner-adjust → Phase 3 preview/save
 *         'photo' → Phase 1 guide-only → Phase 3 preview/save
 *
 * CSP-safe: served from /static/js/ — no inline JS, no CDN dependencies.
 */
(function () {
    'use strict';

    var SCAN_CAM_KEY = 'pms_scan_camera_id';
    var ID_OUT_W     = 900;
    var ID_OUT_H     = 567;

    // Known ID-card aspect ratios  W / H
    // Standard ID / Aadhaar / PAN / DL landscape : ~1.586
    // Passport booklet landscape                 : ~1.42
    // Standard ID portrait                       : ~0.63
    var ID_RATIOS = [1.586, 1.42, 0.63];

    // =========================================================================
    // 1. LINEAR ALGEBRA — 8×8 Gaussian elimination for homography
    // =========================================================================

    function solve8(A, b) {
        var n = 8, M = [], r, col, row, k, f, j, i;
        for (r = 0; r < n; r++) { M.push(A[r].slice()); M[r].push(b[r]); }
        for (col = 0; col < n; col++) {
            var maxRow = col;
            for (row = col + 1; row < n; row++)
                if (Math.abs(M[row][col]) > Math.abs(M[maxRow][col])) maxRow = row;
            var tmp = M[col]; M[col] = M[maxRow]; M[maxRow] = tmp;
            if (Math.abs(M[col][col]) < 1e-10) return null;
            for (r = col + 1; r < n; r++) {
                f = M[r][col] / M[col][col];
                for (k = col; k <= n; k++) M[r][k] -= f * M[col][k];
            }
        }
        var x = new Array(n);
        for (i = n - 1; i >= 0; i--) {
            x[i] = M[i][n];
            for (j = i + 1; j < n; j++) x[i] -= M[i][j] * x[j];
            x[i] /= M[i][i];
        }
        return x;
    }

    function computeHomography(src, dst) {
        var A = [], b = [];
        for (var i = 0; i < 4; i++) {
            var sx = src[i].x, sy = src[i].y, dx = dst[i].x, dy = dst[i].y;
            A.push([sx,sy,1,0,0,0,-sx*dx,-sy*dx]); b.push(dx);
            A.push([0,0,0,sx,sy,1,-sx*dy,-sy*dy]); b.push(dy);
        }
        var h = solve8(A, b);
        return h ? [h[0],h[1],h[2],h[3],h[4],h[5],h[6],h[7],1] : null;
    }

    function applyH(H, x, y) {
        var w = H[6]*x + H[7]*y + H[8];
        return { x: (H[0]*x + H[1]*y + H[2])/w,
                 y: (H[3]*x + H[4]*y + H[5])/w };
    }

    // =========================================================================
    // 2. IMAGE PROCESSING
    // =========================================================================

    function toGray(rgba, w, h) {
        var g = new Uint8Array(w * h);
        for (var i = 0; i < w * h; i++)
            g[i] = (0.299*rgba[i*4] + 0.587*rgba[i*4+1] + 0.114*rgba[i*4+2]) | 0;
        return g;
    }

    var GK = [2,4,5,4,2, 4,9,12,9,4, 5,12,15,12,5, 4,9,12,9,4, 2,4,5,4,2];
    var GS = GK.reduce(function(a,b){return a+b;}, 0); // 159

    function gaussBlur(g, w, h) {
        var o = new Uint8Array(w * h);
        for (var y = 2; y < h-2; y++) for (var x = 2; x < w-2; x++) {
            var s = 0;
            for (var ky = 0; ky < 5; ky++) for (var kx = 0; kx < 5; kx++)
                s += g[(y+ky-2)*w+(x+kx-2)] * GK[ky*5+kx];
            o[y*w+x] = (s/GS) | 0;
        }
        return o;
    }

    // Returns separate X and Y Sobel components as Float32Arrays
    function sobelComponents(g, w, h) {
        var ex = new Float32Array(w*h), ey = new Float32Array(w*h);
        for (var y = 1; y < h-1; y++) for (var x = 1; x < w-1; x++) {
            var i = y*w+x;
            ex[i] = (-g[(y-1)*w+(x-1)] + g[(y-1)*w+(x+1)]
                     -2*g[y*w+(x-1)]    + 2*g[y*w+(x+1)]
                     -g[(y+1)*w+(x-1)]  + g[(y+1)*w+(x+1)]);
            ey[i] = (-g[(y-1)*w+(x-1)] - 2*g[(y-1)*w+x] - g[(y-1)*w+(x+1)]
                     +g[(y+1)*w+(x-1)] + 2*g[(y+1)*w+x]  + g[(y+1)*w+(x+1)]);
        }
        return { ex: ex, ey: ey };
    }

    // Brightness sampled every 2 px within a zone (no whole-frame average).
    function zoneBrightness(gray, w, x1, x2, y1, y2) {
        var s = 0, cnt = 0;
        for (var y = y1; y < y2; y += 2) for (var x = x1; x < x2; x += 2) {
            s += gray[y*w+x]; cnt++;
        }
        return cnt ? s / cnt : 128;
    }

    // Laplacian variance within zone — proxy for sharpness (samples every 2 px).
    function zoneLaplacianVar(gray, w, x1, x2, y1, y2) {
        var h = (gray.length / w) | 0;
        var xa = Math.max(1, x1), xb = Math.min(w-2, x2);
        var ya = Math.max(1, y1), yb = Math.min(h-2, y2);
        var sum = 0, sumSq = 0, cnt = 0;
        for (var y = ya; y < yb; y += 2) for (var x = xa; x < xb; x += 2) {
            var v = -gray[(y-1)*w+x] - gray[y*w+(x-1)] + 4*gray[y*w+x]
                    - gray[y*w+(x+1)] - gray[(y+1)*w+x];
            sum += v; sumSq += v*v; cnt++;
        }
        if (!cnt) return 0;
        var mean = sum / cnt;
        return sumSq / cnt - mean * mean;
    }

    // Local contrast normalisation — min-max histogram stretch within zone.
    // Skip if range < 40 (already sufficient contrast).
    function normalizeGuideContrast(gray, w, x1, x2, y1, y2) {
        var mn = 255, mx = 0, y, x, v;
        for (y = y1; y < y2; y++) for (x = x1; x < x2; x++) {
            v = gray[y*w+x]; if (v < mn) mn = v; if (v > mx) mx = v;
        }
        if (mx - mn < 40) return;
        var range = mx - mn;
        for (y = y1; y < y2; y++) for (x = x1; x < x2; x++)
            gray[y*w+x] = ((gray[y*w+x] - mn) * 255 / range) | 0;
    }

    // =========================================================================
    // 3. CARD DETECTION — projection-based
    //
    //  Why projection beats angular-extrema for ID cards:
    //   • A card edge is a *long continuous line* → contributes to many pixels in
    //     a single row/column → large projection value.
    //   • Fingers, shadows, background objects are *localised* → contribute to few
    //     pixels per row/column → small projection value.
    //  Result: card edges dominate even when a hand is holding the card.
    // =========================================================================

    // Compute row/column edge projections within the search window.
    // hP[y] = average |Sobel_Y| across columns in [sx1,sx2) — detects horiz edges.
    // vP[x] = average |Sobel_X| across rows in [sy1,sy2)   — detects vert  edges.
    function computeProjections(ex, ey, w, sx1, sx2, sy1, sy2) {
        var sw = sx2 - sx1, sh = sy2 - sy1;
        // Allocate full-size arrays but only fill the search-zone slice.
        var hP = new Float32Array(sy2 + 1);
        var vP = new Float32Array(sx2 + 1);
        var y, x, s;
        for (y = sy1; y < sy2; y++) {
            s = 0;
            for (x = sx1; x < sx2; x++) s += Math.abs(ey[y*w+x]);
            hP[y] = sw > 0 ? s / sw : 0;
        }
        for (x = sx1; x < sx2; x++) {
            s = 0;
            for (y = sy1; y < sy2; y++) s += Math.abs(ex[y*w+x]);
            vP[x] = sh > 0 ? s / sh : 0;
        }
        return { hP: hP, vP: vP };
    }

    // Smooth a projection slice and return peaks sorted by value (desc).
    function peaksOf(proj, start, end) {
        // Smooth with half-window of 6 px
        var sm = new Float32Array(end + 1);
        var i, j, s, c;
        for (i = start; i < end; i++) {
            s = 0; c = 0;
            for (j = Math.max(start, i-6); j <= Math.min(end-1, i+6); j++) {
                s += proj[j]; c++;
            }
            sm[i] = c ? s / c : 0;
        }
        var peaks = [];
        for (i = start + 3; i < end - 3; i++) {
            if (sm[i] < 2) continue; // below noise floor
            if (sm[i] >= sm[i-1] && sm[i] >= sm[i+1] &&
                sm[i] >= sm[i-2] && sm[i] >= sm[i+2] &&
                sm[i] >= sm[i-3] && sm[i] >= sm[i+3])
                peaks.push({ pos: i, val: sm[i] });
        }
        return peaks.sort(function(a,b){ return b.val - a.val; });
    }

    // Score how close 'ratio' is to any known ID-card aspect ratio.
    // Returns 0..1 (1 = perfect match).
    function idRatioScore(ratio) {
        var best = 0;
        for (var i = 0; i < ID_RATIOS.length; i++) {
            var s = Math.max(0, 1 - Math.abs(ratio - ID_RATIOS[i]) / ID_RATIOS[i] * 1.8);
            if (s > best) best = s;
        }
        return best;
    }

    // Returns true when two corner sets are close enough to count as the same detection.
    // 2.5 % tolerance (down from 4 %) — tighter for Full HD cameras.
    function cornersStable(c1, c2, VW, VH) {
        if (!c1 || !c2) return false;
        var tx = VW * 0.025, ty = VH * 0.025;
        for (var i = 0; i < 4; i++)
            if (Math.abs(c1[i].x-c2[i].x) > tx || Math.abs(c1[i].y-c2[i].y) > ty)
                return false;
        return true;
    }

    // Reusable off-screen canvas to avoid GC pressure during detection loop.
    var _detectCanvas = null;
    function getDetectCanvas(w, h) {
        if (!_detectCanvas || _detectCanvas.width !== w || _detectCanvas.height !== h) {
            _detectCanvas = document.createElement('canvas');
            _detectCanvas.width = w; _detectCanvas.height = h;
        }
        return _detectCanvas;
    }

    /**
     * detectCard(videoEl)
     *
     * Pipeline:
     *   1. Centre-crop guide zone + 12 % margin from full-HD frame → ≤640 px wide.
     *      This eliminates background entirely and gives 2× more pixels on the card.
     *   2. Zone-only brightness / sharpness gates (no whole-frame averages).
     *   3. Local contrast normalisation within guide zone.
     *   4. Projection-based edge detection constrained strictly to guide zone.
     *   5. Fill-ratio enforcement: card must be ≥65 % of guide width AND height.
     *   6. Scoring: ratio × fill × guide-overlap × edge-strength.
     *   7. Corners mapped back to video pixel space via crop offset.
     *
     * Returns { corners: [{x,y}×4] | null, conf: 0–1, msg: string }
     * corners are in *video* pixel coordinates (TL, TR, BR, BL).
     */
    function detectCard(videoEl) {
        var VW = videoEl.videoWidth, VH = videoEl.videoHeight;
        if (!VW || !VH) return { corners: null, conf: 0, msg: 'Camera initialising…' };

        // ── Guide zone in video space (matches drawGuideRect) ────────────────
        var vgW = VW * 0.72, vgH = vgW / 1.586;
        var vgX = (VW - vgW) / 2,  vgY = (VH - vgH) / 2;

        // Crop = guide zone + 12 % margin on each side
        var mg12 = 0.12;
        var cropX = Math.max(0,  (vgX - vgW * mg12) | 0);
        var cropY = Math.max(0,  (vgY - vgH * mg12) | 0);
        var cropX2 = Math.min(VW, (vgX + vgW * (1 + mg12)) | 0);
        var cropY2 = Math.min(VH, (vgY + vgH * (1 + mg12)) | 0);
        var cropW = cropX2 - cropX, cropH = cropY2 - cropY;
        if (cropW < 10 || cropH < 10) return { corners: null, conf: 0, msg: 'Camera initialising…' };

        // Scale cropped area to ≤640 px wide for detection speed
        var DW = Math.min(640, cropW);
        var DH = ((cropH * DW / cropW) | 0) || 1;

        var tc = getDetectCanvas(DW, DH);
        var tx = tc.getContext('2d');
        // Draw only the cropped guide region, scaled to DW×DH
        tx.drawImage(videoEl, cropX, cropY, cropW, cropH, 0, 0, DW, DH);
        var id = tx.getImageData(0, 0, DW, DH);
        var gray = toGray(id.data, DW, DH);

        // ── Guide zone in detection (DW×DH) space ───────────────────────────
        // Scale factors from video to detection space
        var scaleX = DW / cropW, scaleY = DH / cropH;
        var gX = ((vgX - cropX) * scaleX) | 0;
        var gY = ((vgY - cropY) * scaleY) | 0;
        var gW = (vgW * scaleX) | 0;
        var gH = (vgH * scaleY) | 0;
        // Clamp to canvas bounds
        var gX2 = Math.min(DW, gX + gW), gY2 = Math.min(DH, gY + gH);
        gX = Math.max(0, gX); gY = Math.max(0, gY);
        gW = gX2 - gX; gH = gY2 - gY;
        if (gW < 10 || gH < 10) return { corners: null, conf: 0, msg: 'Place ID card in the guide area', sharpness: 0 };

        // ── Quality gates on guide zone only ─────────────────────────────────
        var bright = zoneBrightness(gray, DW, gX, gX2, gY, gY2);
        if (bright < 35)  return { corners: null, conf: 0, msg: 'Too dark — improve lighting', sharpness: 0 };
        if (bright > 238) return { corners: null, conf: 0, msg: 'Too bright — reduce glare', sharpness: 0 };

        var lapV = zoneLaplacianVar(gray, DW, gX, gX2, gY, gY2);
        if (lapV < 22)    return { corners: null, conf: 0, msg: 'Hold steady for a clear image', sharpness: lapV };

        // ── Local contrast normalisation in guide zone ───────────────────────
        normalizeGuideContrast(gray, DW, gX, gX2, gY, gY2);

        // ── Edge detection ───────────────────────────────────────────────────
        var blur = gaussBlur(gray, DW, DH);
        var sob  = sobelComponents(blur, DW, DH);

        // Search zone = strictly the guide zone (background already removed by crop)
        var sx1 = gX, sy1 = gY, sx2 = gX2, sy2 = gY2;

        var proj   = computeProjections(sob.ex, sob.ey, DW, sx1, sx2, sy1, sy2);
        var hPeaks = peaksOf(proj.hP, sy1, sy2);  // candidate top/bottom rows
        var vPeaks = peaksOf(proj.vP, sx1, sx2);  // candidate left/right cols

        if (!hPeaks.length || !vPeaks.length)
            return { corners: null, conf: 0, msg: 'Place ID card in the guide area', sharpness: lapV };

        // ── Score every (top,bottom)×(left,right) combination ────────────────
        var best = null, bestConf = 0, bestFill = 0;
        var MAX_PEAKS = 8;

        for (var hi = 0; hi < Math.min(hPeaks.length, MAX_PEAKS); hi++) {
            for (var hj = hi+1; hj < Math.min(hPeaks.length, MAX_PEAKS); hj++) {
                var y1p = Math.min(hPeaks[hi].pos, hPeaks[hj].pos);
                var y2p = Math.max(hPeaks[hi].pos, hPeaks[hj].pos);
                var cardH = y2p - y1p;
                if (cardH < DH*0.08 || cardH > DH*0.95) continue;

                for (var vi = 0; vi < Math.min(vPeaks.length, MAX_PEAKS); vi++) {
                    for (var vj = vi+1; vj < Math.min(vPeaks.length, MAX_PEAKS); vj++) {
                        var x1p = Math.min(vPeaks[vi].pos, vPeaks[vj].pos);
                        var x2p = Math.max(vPeaks[vi].pos, vPeaks[vj].pos);
                        var cardW = x2p - x1p;
                        if (cardW < DW*0.08 || cardW > DW*0.95) continue;

                        var ratio = cardW / cardH;
                        var rs    = idRatioScore(ratio);
                        if (rs < 0.15) continue;

                        // Fill ratio: card vs guide zone dimensions
                        var fillW = cardW / gW, fillH = cardH / gH;
                        var fillMin = Math.min(fillW, fillH);
                        // Score fills 0 at 0, peaks at 1.0 (perfectly fills guide)
                        var fillScore = fillMin < 0.65
                            ? fillMin / 0.65
                            : Math.max(0, 1 - (fillMin - 1.0) * 2);

                        // Overlap fraction between detected rect and guide zone
                        var ox = Math.max(0, Math.min(x2p, gX2) - Math.max(x1p, gX));
                        var oy = Math.max(0, Math.min(y2p, gY2) - Math.max(y1p, gY));
                        var overlapFrac = (ox * oy) / (cardW * cardH);

                        // Edge strength
                        var eScore = Math.min(1,
                            (hPeaks[hi].val + hPeaks[hj].val +
                             vPeaks[vi].val + vPeaks[vj].val) / 400);

                        // Combined confidence
                        var conf = rs          * 0.30   // aspect ratio match
                                 + fillScore   * 0.25   // fills guide zone
                                 + overlapFrac * 0.25   // inside guide zone
                                 + eScore      * 0.20;  // edge strength

                        if (conf > bestConf) {
                            bestConf = conf;
                            bestFill = fillMin;
                            best = { x1: x1p, y1: y1p, x2: x2p, y2: y2p, ratio: ratio };
                        }
                    }
                }
            }
        }

        if (!best || bestConf < 0.12)
            return { corners: null, conf: 0, msg: 'Place ID card in the guide area', sharpness: lapV };

        // ── Map detected corners back to video pixel space ───────────────────
        // detX → cropX + detX * (cropW/DW) = video X
        var toVX = cropW / DW, toVY = cropH / DH;
        var corners = [
            { x: cropX + best.x1 * toVX, y: cropY + best.y1 * toVY },  // TL
            { x: cropX + best.x2 * toVX, y: cropY + best.y1 * toVY },  // TR
            { x: cropX + best.x2 * toVX, y: cropY + best.y2 * toVY },  // BR
            { x: cropX + best.x1 * toVX, y: cropY + best.y2 * toVY }   // BL
        ];

        // ── Contextual guidance message ──────────────────────────────────────
        var msg;
        if      (bestConf >= 0.60)  msg = 'Document detected — click <strong>Capture</strong>';
        else if (bestFill < 0.45)   msg = 'Move closer to the ID card';
        else if (bestFill > 1.10)   msg = 'Move camera back a little';
        else                        msg = 'Keep the ID edges visible in the guide area';

        return { corners: corners, conf: bestConf, msg: msg, sharpness: lapV };
    }

    // =========================================================================
    // 4. PERSPECTIVE WARP
    // =========================================================================

    function defaultCorners(videoEl) {
        // Default to the guide zone in video space (matches what the user sees)
        var w = videoEl.videoWidth, h = videoEl.videoHeight;
        if (!w || !h) return null;
        var gw = w * 0.72, gh = gw / 1.586;
        var gx = (w - gw) / 2, gy = (h - gh) / 2;
        return [{ x:gx, y:gy }, { x:gx+gw, y:gy },
                { x:gx+gw, y:gy+gh }, { x:gx, y:gy+gh }];
    }

    function warpPerspective(srcCanvas, corners, outW, outH) {
        var dstPts = [{ x:0,      y:0 },      { x:outW-1, y:0 },
                      { x:outW-1, y:outH-1 }, { x:0,      y:outH-1 }];
        var H = computeHomography(dstPts, corners);
        if (!H) return null;

        var sCtx  = srcCanvas.getContext('2d');
        var sData = sCtx.getImageData(0, 0, srcCanvas.width, srcCanvas.height);
        var sW = srcCanvas.width, sH = srcCanvas.height;
        var out  = document.createElement('canvas');
        out.width = outW; out.height = outH;
        var oCtx = out.getContext('2d');
        var oImg = oCtx.createImageData(outW, outH);
        var oD = oImg.data, sD = sData.data;

        for (var dy = 0; dy < outH; dy++) for (var dx = 0; dx < outW; dx++) {
            var src = applyH(H, dx, dy);
            var sx = src.x, sy = src.y;
            var oi = (dy*outW + dx) * 4;
            if (sx < 0 || sy < 0 || sx >= sW-1 || sy >= sH-1) {
                oD[oi] = oD[oi+1] = oD[oi+2] = 255; oD[oi+3] = 255; continue;
            }
            var x0 = sx|0, y0 = sy|0, fx = sx-x0, fy = sy-y0;
            var i00 = (y0*sW+x0)*4, i10 = i00+4, i01 = i00+sW*4, i11 = i01+4;
            var omx = 1-fx, omy = 1-fy;
            for (var c = 0; c < 3; c++)
                oD[oi+c] = (sD[i00+c]*omx*omy + sD[i10+c]*fx*omy +
                            sD[i01+c]*omx*fy  + sD[i11+c]*fx*fy) | 0;
            oD[oi+3] = 255;
        }
        oCtx.putImageData(oImg, 0, 0);
        return out;
    }

    // =========================================================================
    // 5. IMAGE ENHANCEMENT
    // =========================================================================

    function enhanceDocument(canvas) {
        var ctx = canvas.getContext('2d'), w = canvas.width, h = canvas.height;
        var img = ctx.getImageData(0, 0, w, h), d = img.data;
        var rMin=255,rMax=0, gMin=255,gMax=0, bMin=255,bMax=0;
        for (var i = 0; i < d.length; i += 4) {
            if (d[i]   < rMin) rMin=d[i];   if (d[i]   > rMax) rMax=d[i];
            if (d[i+1] < gMin) gMin=d[i+1]; if (d[i+1] > gMax) gMax=d[i+1];
            if (d[i+2] < bMin) bMin=d[i+2]; if (d[i+2] > bMax) bMax=d[i+2];
        }
        var rR = rMax>rMin?255/(rMax-rMin):1, gR = gMax>gMin?255/(gMax-gMin):1,
            bR = bMax>bMin?255/(bMax-bMin):1;
        for (var i = 0; i < d.length; i += 4) {
            d[i]   = Math.min(255, ((d[i]   - rMin) * rR) | 0);
            d[i+1] = Math.min(255, ((d[i+1] - gMin) * gR) | 0);
            d[i+2] = Math.min(255, ((d[i+2] - bMin) * bR) | 0);
        }
        ctx.putImageData(img, 0, 0);
        var out = document.createElement('canvas');
        out.width = w; out.height = h;
        var oc = out.getContext('2d');
        oc.filter = 'contrast(1.18) brightness(1.04) saturate(1.05)';
        oc.drawImage(canvas, 0, 0);
        return out;
    }

    // =========================================================================
    // 6. OVERLAY DRAWING
    // =========================================================================

    /**
     * drawOverlay — detected card rectangle, coloured by confidence + stability.
     *   Green  : stable (3+ frames) + conf ≥ 0.50 → ready to capture
     *   Amber  : detected but not yet stable / medium confidence
     *   Red    : detected but low confidence (likely a false positive)
     */
    function drawOverlay(canvas, videoEl, corners, conf, stable) {
        var vw = videoEl.videoWidth  || videoEl.offsetWidth;
        var vh = videoEl.videoHeight || videoEl.offsetHeight;
        var dw = videoEl.offsetWidth, dh = videoEl.offsetHeight;
        canvas.width = dw; canvas.height = dh;
        var ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, dw, dh);
        if (!corners) return;

        var sx = dw / (vw || dw), sy = dh / (vh || dh);

        var borderColor, fillColor;
        if (stable && conf >= 0.50) {
            borderColor = '#22c55e'; fillColor = 'rgba(34,197,94,0.08)';
        } else if (conf >= 0.35) {
            borderColor = '#f59e0b'; fillColor = 'rgba(245,158,11,0.08)';
        } else {
            borderColor = '#ef4444'; fillColor = 'rgba(239,68,68,0.08)';
        }

        ctx.beginPath();
        ctx.moveTo(corners[0].x*sx, corners[0].y*sy);
        for (var i = 1; i < 4; i++) ctx.lineTo(corners[i].x*sx, corners[i].y*sy);
        ctx.closePath();
        ctx.strokeStyle = borderColor; ctx.lineWidth = 2.5; ctx.stroke();
        ctx.fillStyle = fillColor; ctx.fill();

        corners.forEach(function(c) {
            ctx.beginPath();
            ctx.arc(c.x*sx, c.y*sy, 5, 0, Math.PI*2);
            ctx.fillStyle = borderColor; ctx.fill();
        });
    }

    /** drawGuideRect — credit-card-shaped guide overlay (shown when nothing detected) */
    function drawGuideRect(canvas, videoEl) {
        var dw = videoEl.offsetWidth  || 640;
        var dh = videoEl.offsetHeight || 360;
        canvas.width = dw; canvas.height = dh;
        var ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, dw, dh);

        var rw = dw * 0.72, rh = rw / 1.586;
        var rx = (dw - rw) / 2, ry = (dh - rh) / 2, cr = 8;

        // Dark vignette outside guide hole
        ctx.fillStyle = 'rgba(0,0,0,0.38)';
        ctx.fillRect(0, 0, dw, dh);
        ctx.clearRect(rx, ry, rw, rh);

        // Rounded border
        ctx.strokeStyle = 'rgba(255,255,255,0.80)'; ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(rx+cr, ry);  ctx.lineTo(rx+rw-cr, ry);
        ctx.quadraticCurveTo(rx+rw, ry,    rx+rw, ry+cr);
        ctx.lineTo(rx+rw, ry+rh-cr);
        ctx.quadraticCurveTo(rx+rw, ry+rh, rx+rw-cr, ry+rh);
        ctx.lineTo(rx+cr, ry+rh);
        ctx.quadraticCurveTo(rx, ry+rh,    rx, ry+rh-cr);
        ctx.lineTo(rx, ry+cr);
        ctx.quadraticCurveTo(rx, ry,        rx+cr, ry);
        ctx.closePath(); ctx.stroke();

        // Corner accent marks
        var cs = 18; ctx.strokeStyle = '#fff'; ctx.lineWidth = 3;
        [[rx,ry,1,1],[rx+rw,ry,-1,1],[rx+rw,ry+rh,-1,-1],[rx,ry+rh,1,-1]]
            .forEach(function(c) {
                ctx.beginPath();
                ctx.moveTo(c[0]+c[2]*cs, c[1]); ctx.lineTo(c[0], c[1]);
                ctx.lineTo(c[0], c[1]+c[3]*cs); ctx.stroke();
            });
    }

    // =========================================================================
    // 7. CORNER DRAG — manual adjustment on phase-2 canvas
    // =========================================================================

    function setupCornerDrag(canvas, corners, onDraw) {
        var HIT = 22, dragIdx = -1;
        function scale() { return canvas.width / canvas.getBoundingClientRect().width; }
        function getPos(e) {
            var r = canvas.getBoundingClientRect(), pt = e.touches ? e.touches[0] : e;
            var sc = scale();
            return { x: (pt.clientX - r.left)*sc, y: (pt.clientY - r.top)*sc };
        }
        function nearest(p) {
            for (var i = 0; i < corners.length; i++) {
                var dx = corners[i].x-p.x, dy = corners[i].y-p.y;
                if (Math.sqrt(dx*dx+dy*dy) < HIT) return i;
            }
            return -1;
        }
        function clamp(v,mn,mx){ return Math.max(mn, Math.min(mx, v)); }
        function onStart(e){ dragIdx = nearest(getPos(e)); if (dragIdx>=0) e.preventDefault(); }
        function onMove(e){
            if (dragIdx < 0) return; e.preventDefault();
            var p = getPos(e);
            corners[dragIdx] = { x: clamp(p.x,0,canvas.width), y: clamp(p.y,0,canvas.height) };
            onDraw(corners);
        }
        function onEnd(){ dragIdx = -1; }
        canvas.addEventListener('mousedown',  onStart);
        canvas.addEventListener('mousemove',  onMove);
        canvas.addEventListener('mouseup',    onEnd);
        canvas.addEventListener('mouseleave', onEnd);
        canvas.addEventListener('touchstart', onStart, { passive: false });
        canvas.addEventListener('touchmove',  onMove,  { passive: false });
        canvas.addEventListener('touchend',   onEnd);
    }

    function drawAdjust(adjustCanvas, capturedCanvas, corners) {
        adjustCanvas.width  = capturedCanvas.width;
        adjustCanvas.height = capturedCanvas.height;
        var ctx = adjustCanvas.getContext('2d');
        ctx.drawImage(capturedCanvas, 0, 0);
        ctx.beginPath();
        ctx.moveTo(corners[0].x, corners[0].y);
        for (var i = 1; i < 4; i++) ctx.lineTo(corners[i].x, corners[i].y);
        ctx.closePath();
        ctx.strokeStyle = 'rgba(34,197,94,0.9)'; ctx.lineWidth = 2; ctx.stroke();
        ctx.fillStyle   = 'rgba(34,197,94,0.10)'; ctx.fill();
        var LABELS = ['TL','TR','BR','BL'];
        corners.forEach(function(c, i) {
            ctx.beginPath(); ctx.arc(c.x, c.y, 10, 0, Math.PI*2);
            ctx.fillStyle = '#22c55e'; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
            ctx.fill(); ctx.stroke();
            ctx.fillStyle = '#fff'; ctx.font = 'bold 9px sans-serif';
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(LABELS[i], c.x, c.y);
        });
    }

    // =========================================================================
    // 8. CAMERA MANAGEMENT
    // =========================================================================

    var STABLE_MS    = 450;
    var scanStream   = null, scanDevices = [], scanRAF = null;
    var stableFrames = 0, lastCorners = null, stableSince = 0;

    var scanVideoEl    = document.getElementById('scanVideo');
    var scanOverlayEl  = document.getElementById('scanOverlay');
    var scanCamSel     = document.getElementById('scanCameraSelect');
    var scanRefreshBtn = document.getElementById('scanRefreshCameras');
    var scanSwitchBtn  = document.getElementById('scanSwitchCamera');
    var scanCamMsg     = document.getElementById('scanCameraMsg');
    var scanDetectMsg  = document.getElementById('scanDetectMsg');

    if (!scanVideoEl) return; // not on this page

    function showScanMsg(text, isErr) {
        if (!scanCamMsg) return;
        scanCamMsg.textContent = text;
        scanCamMsg.className   = 'small mb-2 ' + (isErr ? 'text-danger' : 'text-success');
        scanCamMsg.style.display = text ? '' : 'none';
    }

    function stopScanStream() {
        if (scanStream) { scanStream.getTracks().forEach(function(t){t.stop();}); scanStream = null; }
        if (scanVideoEl) scanVideoEl.srcObject = null;
        if (scanRAF) { cancelAnimationFrame(scanRAF); scanRAF = null; }
    }

    async function populateScanCameras(preferId) {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
            showScanMsg('Camera API not supported.', true); return;
        }
        var devs = await navigator.mediaDevices.enumerateDevices();
        scanDevices = devs.filter(function(d){ return d.kind === 'videoinput'; });
        if (!scanCamSel) return;
        scanCamSel.innerHTML = '';
        if (!scanDevices.length) {
            scanCamSel.innerHTML = '<option value="">No camera detected</option>';
            showScanMsg('No camera detected.', true);
            if (scanSwitchBtn) scanSwitchBtn.classList.add('d-none');
            return;
        }
        var saved = preferId !== undefined ? preferId : (localStorage.getItem(SCAN_CAM_KEY) || '');
        scanDevices.forEach(function(d, i) {
            var o = document.createElement('option');
            o.value = d.deviceId; o.textContent = d.label || ('Camera ' + (i+1));
            scanCamSel.appendChild(o);
        });
        var found = scanDevices.some(function(d){ return d.deviceId === saved; });
        scanCamSel.value = found ? saved : scanDevices[0].deviceId;
        if (scanSwitchBtn) scanSwitchBtn.classList.toggle('d-none', scanDevices.length < 2);
        showScanMsg('', false);
    }

    async function startScanCamera(deviceId) {
        stopScanStream(); showScanMsg('', false);
        var constraints = { video: deviceId
            ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
            : { width: { ideal: 1280 }, height: { ideal: 720 } } };
        try {
            scanStream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch(err) {
            if (deviceId && (err.name === 'OverconstrainedError' || err.name === 'NotFoundError')) {
                showScanMsg('Camera unavailable. Using default.', true);
                try { scanStream = await navigator.mediaDevices.getUserMedia({ video: true }); }
                catch(e) { showScanMsg('Camera access denied. Please allow camera permission.', true); return false; }
            } else if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                showScanMsg('Camera access denied. Please allow camera permission in your browser.', true); return false;
            } else {
                showScanMsg('Camera not available: ' + err.message, true); return false;
            }
        }
        // Refresh labels after permission granted (were placeholders before)
        if (scanCamSel && scanCamSel.options.length && /^Camera \d+$/.test(scanCamSel.options[0].textContent)) {
            var runId = scanStream.getVideoTracks()[0].getSettings().deviceId;
            await populateScanCameras(runId || deviceId);
        }
        scanVideoEl.srcObject = scanStream;
        await new Promise(function(resolve){ scanVideoEl.onloadedmetadata = resolve; });
        scanVideoEl.play().catch(function(){});
        return true;
    }

    // =========================================================================
    // 9. DETECTION LOOP
    // =========================================================================

    var currentSide    = 'front';
    var currentMode    = 'scan';   // 'scan' | 'photo' | 'stand'
    var lastDetectTime = 0;

    // ── Focus bar helpers (for stand mode) ───────────────────────────────────
    var scanFocusBarWrap = document.getElementById('scanFocusBarWrap');
    var scanFocusBar     = document.getElementById('scanFocusBar');
    var scanFocusLabel   = document.getElementById('scanFocusLabel');

    function updateFocusBar(sharpness) {
        if (!scanFocusBar || !scanFocusLabel) return;
        var pct = Math.min(100, Math.max(0, (sharpness / 200) * 100));
        scanFocusBar.style.width = pct + '%';
        var color, label;
        if (sharpness < 22)       { color = 'bg-danger';  label = 'Blurry'; }
        else if (sharpness < 50)  { color = 'bg-warning'; label = 'Focusing\u2026'; }
        else if (sharpness < 100) { color = 'bg-info';    label = 'Almost sharp'; }
        else                      { color = 'bg-success'; label = sharpness >= 200 ? 'Very sharp' : 'Sharp'; }
        scanFocusBar.className = 'progress-bar ' + color;
        scanFocusLabel.textContent = label;
    }

    function detectionLoop() {
        scanRAF = requestAnimationFrame(function(ts) {
            if (ts - lastDetectTime > 300) {
                lastDetectTime = ts;
                if (scanVideoEl.readyState >= 2) {
                    if (currentMode === 'photo') {
                        // Quick Photo: just show the ID guide rectangle
                        drawGuideRect(scanOverlayEl, scanVideoEl);
                    } else if (currentMode === 'stand') {
                        // Stand mode: detection for visual feedback + focus bar, no cropping
                        var res = detectCard(scanVideoEl);
                        updateFocusBar(res ? res.sharpness : 0);
                        if (res && res.corners) {
                            var VW = scanVideoEl.videoWidth, VH = scanVideoEl.videoHeight;
                            if (cornersStable(lastCorners, res.corners, VW, VH)) {
                                stableFrames++;
                                if (!stableSince) stableSince = Date.now();
                            } else {
                                stableFrames = 1;
                                stableSince  = 0;
                            }
                            lastCorners = res.corners;

                            var elapsed = stableSince ? (Date.now() - stableSince) : 0;
                            var stable  = stableFrames >= 2 &&
                                          elapsed >= STABLE_MS &&
                                          res.conf >= 0.45;
                            drawOverlay(scanOverlayEl, scanVideoEl, res.corners, res.conf, stable);

                            if (scanDetectMsg) {
                                if (stable && res.conf >= 0.55 && res.sharpness >= 50) {
                                    scanDetectMsg.innerHTML =
                                        '<i class="bi bi-check-circle-fill text-success me-1"></i>' +
                                        'In focus — click <strong>Capture</strong>';
                                } else if (res.sharpness < 50) {
                                    scanDetectMsg.innerHTML =
                                        '<i class="bi bi-eye me-1"></i>Waiting for autofocus\u2026';
                                } else {
                                    scanDetectMsg.innerHTML =
                                        '<i class="bi bi-search me-1"></i>' + res.msg;
                                }
                            }
                        } else {
                            stableFrames = 0; lastCorners = null; stableSince = 0;
                            drawGuideRect(scanOverlayEl, scanVideoEl);
                            if (scanDetectMsg) {
                                var msg2 = res && res.msg ? res.msg : 'Place ID card under the camera';
                                scanDetectMsg.innerHTML =
                                    '<i class="bi bi-info-circle me-1"></i>' + msg2;
                            }
                        }
                    } else {
                        // Scan mode: run projection-based card detection
                        var res = detectCard(scanVideoEl);
                        if (res && res.corners) {
                            var VW = scanVideoEl.videoWidth, VH = scanVideoEl.videoHeight;
                            if (cornersStable(lastCorners, res.corners, VW, VH)) {
                                stableFrames++;
                                if (!stableSince) stableSince = Date.now();
                            } else {
                                stableFrames = 1;
                                stableSince  = 0;
                            }
                            lastCorners = res.corners;

                            var elapsed = stableSince ? (Date.now() - stableSince) : 0;
                            var stable  = stableFrames >= 2 &&
                                          elapsed >= STABLE_MS &&
                                          res.conf >= 0.45;
                            drawOverlay(scanOverlayEl, scanVideoEl, res.corners, res.conf, stable);

                            if (scanDetectMsg) {
                                if (stable && res.conf >= 0.55) {
                                    scanDetectMsg.innerHTML =
                                        '<i class="bi bi-check-circle-fill text-success me-1"></i>' +
                                        'Document detected — click <strong>Capture</strong>';
                                } else if (stableFrames >= 2 && elapsed < STABLE_MS) {
                                    scanDetectMsg.innerHTML =
                                        '<i class="bi bi-hourglass-split me-1"></i>Hold steady…';
                                } else {
                                    scanDetectMsg.innerHTML =
                                        '<i class="bi bi-search me-1"></i>' + res.msg;
                                }
                            }
                        } else {
                            stableFrames = 0; lastCorners = null; stableSince = 0;
                            drawGuideRect(scanOverlayEl, scanVideoEl);
                            if (scanDetectMsg) {
                                var msg = res && res.msg ? res.msg : 'Place ID card in the guide area';
                                scanDetectMsg.innerHTML =
                                    '<i class="bi bi-info-circle me-1"></i>' + msg + '.';
                            }
                        }
                    }
                }
            }
            if (scanStream) detectionLoop();
        });
    }

    // =========================================================================
    // 10. MODAL PHASE CONTROLLER
    // =========================================================================

    var capturedCanvas       = null;
    var adjustCorners        = null;
    var scanPhase1El         = document.getElementById('scanPhase1');
    var scanPhase2El         = document.getElementById('scanPhase2');
    var scanPhase3El         = document.getElementById('scanPhase3');
    var scanAdjustCanvas     = document.getElementById('scanAdjustCanvas');
    var scanResultImg        = document.getElementById('scanResultImg');
    var docScannerModal      = document.getElementById('docScannerModal');
    var docScannerSideLabel  = document.getElementById('docScannerSideLabel');
    var docScannerModeIcon   = document.getElementById('docScannerModeIcon');
    var docScannerModeText   = document.getElementById('docScannerModeText');
    var scanAdjustCornersBtn = document.getElementById('scanAdjustCornersBtn');

    var bsModal = (typeof bootstrap !== 'undefined') && docScannerModal
        ? new bootstrap.Modal(docScannerModal, { backdrop: 'static', keyboard: false })
        : null;

    function showPhase(n) {
        [scanPhase1El, scanPhase2El, scanPhase3El].forEach(function(el, i) {
            if (el) el.style.display = (i+1 === n) ? '' : 'none';
        });
    }

    // ── Capture (phase 1 → 2 for scan, phase 1 → 3 for photo) ──────────────
    var scanCaptureBtn = document.getElementById('scanCaptureBtn');
    if (scanCaptureBtn) {
        scanCaptureBtn.addEventListener('click', function() {
            if (!scanVideoEl.videoWidth) return;
            capturedCanvas = document.createElement('canvas');
            capturedCanvas.width  = scanVideoEl.videoWidth;
            capturedCanvas.height = scanVideoEl.videoHeight;
            capturedCanvas.getContext('2d').drawImage(scanVideoEl, 0, 0);
            stopScanStream();

            if (currentMode === 'photo') {
                // Quick Photo: skip corner adjustment, go directly to preview
                if (scanResultImg) scanResultImg.src = capturedCanvas.toDataURL('image/jpeg', 0.90);
                if (scanAdjustCornersBtn) scanAdjustCornersBtn.style.display = 'none';
                showPhase(3);
            } else if (currentMode === 'stand') {
                // Stand mode: skip corner adjustment, apply enhancement, go to preview
                var enhanced = enhanceDocument(capturedCanvas);
                if (scanResultImg) scanResultImg.src = (enhanced || capturedCanvas).toDataURL('image/jpeg', 0.92);
                if (scanAdjustCornersBtn) scanAdjustCornersBtn.style.display = 'none';
                showPhase(3);
            } else {
                // Scan mode: use detected corners (or guide zone fallback) for adjustment
                adjustCorners = (lastCorners && lastCorners.length === 4)
                    ? lastCorners.map(function(c){ return { x: c.x, y: c.y }; })
                    : defaultCorners(scanVideoEl);
                showPhase(2);
                drawAdjust(scanAdjustCanvas, capturedCanvas, adjustCorners);
                setupCornerDrag(scanAdjustCanvas, adjustCorners, function(corners) {
                    drawAdjust(scanAdjustCanvas, capturedCanvas, corners);
                });
            }
        });
    }

    // ── Retake (phase 2 → phase 1) ───────────────────────────────────────────
    var scanRetakeBtn = document.getElementById('scanRetakeBtn');
    if (scanRetakeBtn) {
        scanRetakeBtn.addEventListener('click', function() {
            showPhase(1); stableFrames = 0; lastCorners = null; stableSince = 0;
            var id = scanCamSel ? scanCamSel.value : '';
            startScanCamera(id).then(function(ok){ if (ok) detectionLoop(); });
        });
    }

    // ── Apply Crop (phase 2 → phase 3) ───────────────────────────────────────
    var scanApplyBtn = document.getElementById('scanApplyBtn');
    if (scanApplyBtn) {
        scanApplyBtn.addEventListener('click', function() {
            scanApplyBtn.disabled = true;
            scanApplyBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Processing…';
            setTimeout(function() {
                var warped   = warpPerspective(capturedCanvas, adjustCorners, ID_OUT_W, ID_OUT_H);
                var enhanced = warped ? enhanceDocument(warped) : capturedCanvas;
                if (scanResultImg) scanResultImg.src = enhanced.toDataURL('image/jpeg', 0.90);
                if (scanAdjustCornersBtn) scanAdjustCornersBtn.style.display = '';
                showPhase(3);
                scanApplyBtn.disabled = false;
                scanApplyBtn.innerHTML = '<i class="bi bi-crop me-1"></i>Apply Crop &amp; Enhance';
            }, 30);
        });
    }

    // ── Adjust Corners (phase 3 → phase 2, scan mode only) ──────────────────
    if (scanAdjustCornersBtn) {
        scanAdjustCornersBtn.addEventListener('click', function() {
            if (!capturedCanvas || !adjustCorners) return;
            showPhase(2);
            drawAdjust(scanAdjustCanvas, capturedCanvas, adjustCorners);
            setupCornerDrag(scanAdjustCanvas, adjustCorners, function(corners) {
                drawAdjust(scanAdjustCanvas, capturedCanvas, corners);
            });
        });
    }

    // ── Retake from phase 3 (phase 3 → phase 1) ─────────────────────────────
    var scanRescanBtn = document.getElementById('scanRescanBtn');
    if (scanRescanBtn) {
        scanRescanBtn.addEventListener('click', function() {
            showPhase(1); stableFrames = 0; lastCorners = null; stableSince = 0;
            var id = scanCamSel ? scanCamSel.value : '';
            startScanCamera(id).then(function(ok){ if (ok) detectionLoop(); });
        });
    }

    // ── Save — commit result to form hidden inputs ───────────────────────────
    var scanUseBtn = document.getElementById('scanUseBtn');
    if (scanUseBtn) {
        scanUseBtn.addEventListener('click', function() {
            var dataUrl = scanResultImg ? scanResultImg.src : '';
            if (!dataUrl) return;
            commitSide(currentSide, dataUrl, currentMode);
            if (bsModal) bsModal.hide();
        });
    }

    // ── Camera selector ───────────────────────────────────────────────────────
    if (scanCamSel) {
        scanCamSel.addEventListener('change', async function() {
            var id = this.value; if (!id) return;
            localStorage.setItem(SCAN_CAM_KEY, id);
            if (scanStream) {
                var ok = await startScanCamera(id);
                if (ok) { stableFrames = 0; lastCorners = null; stableSince = 0; detectionLoop(); }
            }
        });
    }

    // ── Refresh cameras ───────────────────────────────────────────────────────
    if (scanRefreshBtn) {
        scanRefreshBtn.addEventListener('click', async function() {
            if (!scanStream) {
                try {
                    var tmp = await navigator.mediaDevices.getUserMedia({ video: true });
                    tmp.getTracks().forEach(function(t){ t.stop(); });
                } catch(e) {
                    showScanMsg('Camera access denied. Please allow camera permission.', true); return;
                }
            }
            await populateScanCameras(scanCamSel ? scanCamSel.value : '');
            showScanMsg('Camera list refreshed.', false);
            setTimeout(function(){ showScanMsg('', false); }, 2500);
        });
    }

    // ── Switch camera ─────────────────────────────────────────────────────────
    if (scanSwitchBtn) {
        scanSwitchBtn.addEventListener('click', async function() {
            if (scanDevices.length < 2) return;
            var cur = scanCamSel ? scanCamSel.value : '';
            var idx = scanDevices.findIndex(function(d){ return d.deviceId === cur; });
            var next = scanDevices[(idx+1) % scanDevices.length].deviceId;
            if (scanCamSel) scanCamSel.value = next;
            localStorage.setItem(SCAN_CAM_KEY, next);
            var ok = await startScanCamera(next);
            if (ok) { stableFrames = 0; lastCorners = null; stableSince = 0; detectionLoop(); }
        });
    }

    // ── Open modal ────────────────────────────────────────────────────────────
    async function openScannerModal(side, sideLabel, mode) {
        currentSide = side; currentMode = mode || 'stand';
        if (docScannerSideLabel) docScannerSideLabel.textContent = sideLabel;
        if (docScannerModeIcon)
            docScannerModeIcon.className = currentMode === 'photo'
                ? 'bi bi-camera me-1'
                : currentMode === 'stand'
                ? 'bi bi-easel me-1'
                : 'bi bi-upc-scan me-1';
        if (docScannerModeText)
            docScannerModeText.textContent = currentMode === 'photo'
                ? 'Quick Photo'
                : currentMode === 'stand'
                ? 'Stand Scanner'
                : 'Scan Document';
        if (scanDetectMsg)
            scanDetectMsg.innerHTML = currentMode === 'photo'
                ? '<i class="bi bi-camera me-1"></i>Position the ID in the guide area, then click <strong>Capture</strong>.'
                : currentMode === 'stand'
                ? '<i class="bi bi-easel me-1"></i>Place ID card under the camera. Wait for focus, then click <strong>Capture</strong>.'
                : '<i class="bi bi-info-circle me-1"></i>Place ID card in the guide area. Detection starts automatically.';
        // Show/hide focus bar for stand mode
        if (scanFocusBarWrap) scanFocusBarWrap.style.display = currentMode === 'stand' ? '' : 'none';
        if (scanFocusBar) { scanFocusBar.style.width = '0%'; scanFocusBar.className = 'progress-bar'; }
        if (scanFocusLabel) scanFocusLabel.textContent = '--';
        stableFrames = 0; lastCorners = null; stableSince = 0;
        showPhase(1);
        if (bsModal) bsModal.show();
        await populateScanCameras();
        var deviceId = scanCamSel ? scanCamSel.value : '';
        var ok = await startScanCamera(deviceId);
        if (ok) { if (deviceId) localStorage.setItem(SCAN_CAM_KEY, deviceId); detectionLoop(); }
    }

    // ── Modal close: stop stream ──────────────────────────────────────────────
    if (docScannerModal) {
        docScannerModal.addEventListener('hidden.bs.modal', function() {
            stopScanStream(); stableFrames = 0; lastCorners = null; stableSince = 0;
        });
    }

    // =========================================================================
    // 11. SIDE PANEL UI
    // =========================================================================

    function commitSide(side, dataUrl, modeName) {
        var S = side === 'front' ? 'Front' : 'Back';
        var dataInput  = document.getElementById('id' + S + 'Data');
        var modeInput  = document.getElementById('id' + S + 'ModeHidden');
        var previewBox = document.getElementById('id' + S + 'PreviewBox');
        var previewImg = document.getElementById('id' + S + 'PreviewImg');
        var modeBadge  = document.getElementById('id' + S + 'ModeBadge');
        if (dataInput)  dataInput.value  = dataUrl;
        if (modeInput)  modeInput.value  = modeName;
        if (previewImg) previewImg.src   = dataUrl;
        if (previewBox) previewBox.style.display = '';
        var labels = { scan: 'Scanned', photo: 'Photo', upload: 'Uploaded', stand: 'Scanned' };
        if (modeBadge) modeBadge.textContent = labels[modeName] || modeName;
    }

    function clearSide(side) {
        var S = side === 'front' ? 'Front' : 'Back';
        var dataInput  = document.getElementById('id' + S + 'Data');
        var modeInput  = document.getElementById('id' + S + 'ModeHidden');
        var previewBox = document.getElementById('id' + S + 'PreviewBox');
        var fileInput  = document.getElementById(side === 'front' ? 'idFront' : 'idBack');
        if (dataInput)  dataInput.value  = '';
        if (modeInput)  modeInput.value  = 'upload';
        if (previewBox) previewBox.style.display = 'none';
        if (fileInput)  fileInput.value  = '';
    }

    // ── Scan Document / Quick Photo buttons ───────────────────────────────────
    ['front', 'back'].forEach(function(side) {
        var S = side === 'front' ? 'Front' : 'Back';
        var sideLabel = S + ' Side';
        var scanBtn  = document.getElementById('id' + S + 'ScanBtn');
        var photoBtn = document.getElementById('id' + S + 'PhotoBtn');
        if (scanBtn)  scanBtn.addEventListener('click',  function(e){ openScannerModal(side, sideLabel, e.shiftKey ? 'scan' : 'stand');  });
        if (photoBtn) photoBtn.addEventListener('click', function(){ openScannerModal(side, sideLabel, 'photo'); });
    });

    // ── Redo (retake) buttons ─────────────────────────────────────────────────
    ['front', 'back'].forEach(function(side) {
        var S = side === 'front' ? 'Front' : 'Back';
        var btn = document.getElementById('id' + S + 'RetakeBtn');
        if (btn) btn.addEventListener('click', function(){ clearSide(side); });
    });

    // ── File upload: show preview immediately ─────────────────────────────────
    ['front', 'back'].forEach(function(side) {
        var fileEl = document.getElementById(side === 'front' ? 'idFront' : 'idBack');
        if (!fileEl) return;
        fileEl.addEventListener('change', function() {
            var file = this.files[0]; if (!file) return;
            var reader = new FileReader();
            reader.onload = function(ev) {
                var S = side === 'front' ? 'Front' : 'Back';
                var previewBox = document.getElementById('id' + S + 'PreviewBox');
                var previewImg = document.getElementById('id' + S + 'PreviewImg');
                var modeBadge  = document.getElementById('id' + S + 'ModeBadge');
                var dataInput  = document.getElementById('id' + S + 'Data');
                if (previewImg) previewImg.src = ev.target.result;
                if (previewBox) previewBox.style.display = '';
                if (modeBadge)  modeBadge.textContent = 'Uploaded';
                if (dataInput)  dataInput.value = ev.target.result;
            };
            reader.readAsDataURL(file);
        });
    });

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() { populateScanCameras(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();

}());
