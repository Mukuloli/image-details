// ===================================================================
// Direct Image-to-Image Virtual Try-On — Client-Side Logic
// ===================================================================

// State
let sourceImageFile = null;
let targetImageFile = null;
let sourceImageDataUrl = null;

// DOM Elements
const sourceUpload = document.getElementById('source-upload');
const sourceInput = document.getElementById('source-input');
const targetUpload = document.getElementById('target-upload');
const targetInput = document.getElementById('target-input');
const generateBtn = document.getElementById('generate-btn');
const originalDisplay = document.getElementById('original-display');
const generatedDisplay = document.getElementById('generated-display');
const downloadBtn = document.getElementById('download-btn');
const statusBar = document.getElementById('status-bar');
const statusText = document.getElementById('status-text');
const genText = document.getElementById('generation-text');

// ---------------------------------------------------------------
// Upload Zone Handlers
// ---------------------------------------------------------------

function setupUploadZone(zone, input, previewEl, onFile) {
    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleFile(file, zone, previewEl, onFile);
        }
    });

    input.addEventListener('change', () => {
        const file = input.files[0];
        if (file) {
            handleFile(file, zone, previewEl, onFile);
        }
    });
}

function handleFile(file, zone, previewEl, onFile) {
    const reader = new FileReader();
    reader.onload = (e) => {
        zone.classList.add('has-image');
        zone.innerHTML = `<img src="${e.target.result}" alt="Preview">`;
        zone.onclick = () => {
            const newInput = document.createElement('input');
            newInput.type = 'file';
            newInput.accept = 'image/*';
            newInput.onchange = () => {
                const f = newInput.files[0];
                if (f) handleFile(f, zone, previewEl, onFile);
            };
            newInput.click();
        };

        if (previewEl) {
            previewEl.innerHTML = `<img src="${e.target.result}" alt="Original">`;
        }

        onFile(file, e.target.result);
    };
    reader.readAsDataURL(file);
}

// Initialize upload zones
setupUploadZone(sourceUpload, sourceInput, originalDisplay, (file, dataUrl) => {
    sourceImageFile = file;
    sourceImageDataUrl = dataUrl;
    checkReady();
    showStatus('info', 'Source image loaded');
});

setupUploadZone(targetUpload, targetInput, null, (file) => {
    targetImageFile = file;
    checkReady();
    showStatus('info', 'Target image loaded');
});

function checkReady() {
    if (sourceImageFile && targetImageFile) {
        generateBtn.disabled = false;
        showStatus('success', '✅ Both images loaded — ready to generate!');
    }
}

// ---------------------------------------------------------------
// Status Bar
// ---------------------------------------------------------------

function showStatus(type, message) {
    statusBar.className = `status-bar ${type} visible`;
    statusText.textContent = message;
}

function hideStatus() {
    statusBar.classList.remove('visible');
}

// ---------------------------------------------------------------
// Pipeline Progress
// ---------------------------------------------------------------

function setPipelineStep(activeStep) {
    const steps = ['pipe-generate', 'pipe-verify', 'pipe-refine'];
    const pipeline = document.getElementById('pipeline-progress');
    pipeline.classList.add('visible');

    steps.forEach(id => {
        const el = document.getElementById(id);
        el.classList.remove('active', 'done');
    });

    const activeIndex = steps.indexOf(activeStep);
    for (let i = 0; i < activeIndex; i++) {
        document.getElementById(steps[i]).classList.add('done');
    }
    if (activeIndex >= 0) {
        document.getElementById(steps[activeIndex]).classList.add('active');
    }
}

function completePipelineStep(stepId) {
    const el = document.getElementById(stepId);
    el.classList.remove('active');
    el.classList.add('done');
}

function resetPipeline() {
    const steps = ['pipe-generate', 'pipe-verify', 'pipe-refine'];
    steps.forEach(id => {
        const el = document.getElementById(id);
        el.classList.remove('active', 'done');
    });
}

// ---------------------------------------------------------------
// Generate Image — Direct Pipeline (No Analysis)
// ---------------------------------------------------------------

generateBtn.addEventListener('click', async () => {
    if (!targetImageFile || !sourceImageFile) return;

    generateBtn.disabled = true;
    generateBtn.classList.add('loading');
    showStatus('info', '🚀 Generating — copying outfit onto target...');
    setPipelineStep('pipe-generate');

    generatedDisplay.innerHTML = `
        <div class="output-placeholder">
            <div class="icon">⏳</div>
            <p>Generating... copying outfit directly</p>
            <p class="pipeline-hint">Generate → Verify → Refine (if needed)</p>
        </div>`;

    // Hide previous results
    document.getElementById('accuracy-badge').style.display = 'none';
    document.getElementById('comparison-section').style.display = 'none';
    document.getElementById('corrections-log').style.display = 'none';
    downloadBtn.classList.remove('visible');
    genText.classList.remove('visible');

    const userInstructions = document.getElementById('user-instructions')?.value || '';

    const formData = new FormData();
    formData.append('source_image', sourceImageFile);
    formData.append('target_image', targetImageFile);
    formData.append('user_instructions', userInstructions);

    try {
        // Update status during the long wait
        const statusUpdater = setInterval(() => {
            const current = statusText.textContent;
            if (current.includes('Generating')) {
                showStatus('info', '🔍 Verifying dress details against source...');
                setPipelineStep('pipe-verify');
            } else if (current.includes('Verifying')) {
                showStatus('info', '🔧 Refining any differences...');
                setPipelineStep('pipe-refine');
            }
        }, 20000);

        const resp = await fetch('/api/generate-direct', {
            method: 'POST',
            body: formData,
        });

        clearInterval(statusUpdater);

        const data = await resp.json();

        if (!resp.ok || !data.success) {
            throw new Error(data.error || 'Generation failed');
        }

        const imgSrc = `data:image/png;base64,${data.image}`;
        generatedDisplay.innerHTML = `<img src="${imgSrc}" alt="Generated Result">`;

        downloadBtn.classList.add('visible');
        downloadBtn.onclick = () => downloadImage(imgSrc, 'generated_outfit.png');

        // Show accuracy badge
        if (data.verification_score !== undefined && data.verification_score >= 0) {
            showAccuracyBadge(data.verification_score);
        }

        // Show comparison view
        if (sourceImageDataUrl) {
            showComparison(sourceImageDataUrl, imgSrc);
        }

        // Show corrections log
        if (data.corrections_applied && data.corrections_applied.length > 0) {
            showCorrectionsLog(data.corrections_applied, data.verification_score);
        }

        if (data.text) {
            genText.textContent = data.text;
            genText.classList.add('visible');
        }

        // Complete all pipeline steps
        completePipelineStep('pipe-generate');
        completePipelineStep('pipe-verify');
        completePipelineStep('pipe-refine');

        const scoreInfo = data.verification_score >= 0
            ? ` (${data.verification_score}% match)`
            : '';
        const refinedInfo = data.corrections_applied?.length > 0
            ? ` — ${data.corrections_applied.length} refinement round(s)`
            : '';
        showStatus('success', `✅ Done!${scoreInfo}${refinedInfo}`);

        // Smooth scroll to result
        generatedDisplay.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Highlight glow effect
        generatedDisplay.parentElement.classList.add('highlight-result');
        setTimeout(() => {
            generatedDisplay.parentElement.classList.remove('highlight-result');
        }, 3000);

    } catch (err) {
        showStatus('error', `Generation failed: ${err.message}`);
        generatedDisplay.innerHTML = `
            <div class="output-placeholder">
                <div class="icon">❌</div>
                <p>Generation failed — try again</p>
            </div>`;
        resetPipeline();
        console.error(err);
    } finally {
        generateBtn.disabled = false;
        generateBtn.classList.remove('loading');
    }
});

// ---------------------------------------------------------------
// Accuracy Badge
// ---------------------------------------------------------------

function showAccuracyBadge(score) {
    const badge = document.getElementById('accuracy-badge');
    const scoreEl = document.getElementById('accuracy-score');
    scoreEl.textContent = `${score}%`;

    // Color code: green >= 90, yellow >= 70, red < 70
    badge.classList.remove('score-high', 'score-mid', 'score-low');
    if (score >= 90) {
        badge.classList.add('score-high');
    } else if (score >= 70) {
        badge.classList.add('score-mid');
    } else {
        badge.classList.add('score-low');
    }
    badge.style.display = 'flex';
}

// ---------------------------------------------------------------
// Comparison View
// ---------------------------------------------------------------

function showComparison(sourceSrc, generatedSrc) {
    const section = document.getElementById('comparison-section');
    const compareSource = document.getElementById('compare-source');
    const compareGenerated = document.getElementById('compare-generated');

    compareSource.innerHTML = `<img src="${sourceSrc}" alt="Source Dress">`;
    compareGenerated.innerHTML = `<img src="${generatedSrc}" alt="Generated Result">`;
    section.style.display = 'block';
}

// ---------------------------------------------------------------
// Corrections Log
// ---------------------------------------------------------------

function showCorrectionsLog(corrections, finalScore) {
    const logSection = document.getElementById('corrections-log');
    const content = document.getElementById('corrections-content');

    let html = '';
    corrections.forEach(round => {
        html += `<div class="correction-round">
            <div class="round-header">
                <span class="round-badge">Round ${round.round}</span>
                <span class="round-score">Score before: ${round.score_before}%</span>
            </div>
            <div class="round-fixes">`;

        round.features.forEach((feature, i) => {
            const fix = round.fixes[i] || '';
            html += `<div class="fix-item">
                <span class="fix-feature">🔧 ${feature}</span>
                <span class="fix-detail">${fix}</span>
            </div>`;
        });

        html += `</div></div>`;
    });

    if (finalScore >= 0) {
        const scoreClass = finalScore >= 90 ? 'score-high' : finalScore >= 70 ? 'score-mid' : 'score-low';
        html += `<div class="final-score-bar ${scoreClass}">
            Final Match Score: <strong>${finalScore}%</strong>
        </div>`;
    }

    content.innerHTML = html;
    logSection.style.display = 'block';
}

// ---------------------------------------------------------------
// Download Image
// ---------------------------------------------------------------

function downloadImage(dataUrl, filename) {
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}
