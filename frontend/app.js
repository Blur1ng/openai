// Глобальные переменные
let selectedFile = null;
let currentBatchId = null;
let pollingInterval = null;

// DOM элементы
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const removeFileBtn = document.getElementById('removeFile');
const submitBtn = document.getElementById('submitBtn');
const progressSection = document.getElementById('progressSection');
const progressStatus = document.getElementById('progressStatus');
const progressBarFill = document.getElementById('progressBarFill');
const resultsGrid = document.getElementById('resultsGrid');
const downloadAllBtn = document.getElementById('downloadAllBtn');
const errorMessage = document.getElementById('errorMessage');
const aiModel = document.getElementById('aiModel');
const model = document.getElementById('model');

// Загрузка сохраненных настроек из localStorage
window.addEventListener('DOMContentLoaded', () => {
    const savedAiModel = localStorage.getItem('aiModel');
    const savedModel = localStorage.getItem('model');
    
    if (savedAiModel) aiModel.value = savedAiModel;
    if (savedModel) model.value = savedModel;
    
    updateModelOptions();
});

// Сохранение настроек при изменении
aiModel.addEventListener('change', () => {
    localStorage.setItem('aiModel', aiModel.value);
    updateModelOptions();
});
model.addEventListener('change', () => localStorage.setItem('model', model.value));

// Обновление опций модели в зависимости от выбранной AI
function updateModelOptions() {
    const modelOptions = {
        chatgpt: [
            { value: 'gpt-4o-mini', text: 'GPT-4o Mini' },
            { value: 'gpt-4o', text: 'GPT-4o' },
            { value: 'gpt-4-turbo', text: 'GPT-4 Turbo' }
        ],
        deepseek: [
            { value: 'deepseek-chat', text: 'DeepSeek Chat' },
            { value: 'deepseek-coder', text: 'DeepSeek Coder' }
        ],
        sonnet: [
            { value: 'claude-3-5-sonnet-20241022', text: 'Claude 3.5 Sonnet' },
            { value: 'claude-3-sonnet-20240229', text: 'Claude 3 Sonnet' }
        ]
    };

    const options = modelOptions[aiModel.value] || modelOptions.chatgpt;
    model.innerHTML = options.map(opt => 
        `<option value="${opt.value}">${opt.text}</option>`
    ).join('');
}

// Обработка drag and drop
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileSelect(files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
    }
});

removeFileBtn.addEventListener('click', () => {
    selectedFile = null;
    fileInfo.classList.remove('show');
    submitBtn.disabled = true;
    fileInput.value = '';
});

// Обработка выбора файла
function handleFileSelect(file) {
    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    fileInfo.classList.add('show');
    submitBtn.disabled = false;
    hideError();
}

// Форматирование размера файла
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Отправка файла на обработку
submitBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    
    submitBtn.disabled = true;
    submitBtn.innerHTML = 'Отправка... <div class="spinner"></div>';
    hideError();
    
    try {
        // Читаем содержимое файла
        const fileContent = await readFileContent(selectedFile);
        
        // Отправляем на API (используем относительный путь)
        const response = await fetch('/api/v1/ai_model/send_prompt/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ai_model: aiModel.value,
                model: model.value,
                request: fileContent
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status}: ${response.statusText}` }));
            throw new Error(errorData.detail || 'Ошибка при отправке запроса');
        }
        
        const data = await response.json();
        currentBatchId = data.batch_id;
        
        // Показываем прогресс
        progressSection.classList.add('show');
        progressStatus.textContent = `0 / ${data.total}`;
        
        // Инициализируем карточки результатов
        initializeResultCards(data.jobs);
        
        // Начинаем polling
        startPolling();
        
    } catch (error) {
        console.error('Error:', error);
        showError(error.message);
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Получить документацию';
    }
});

// Чтение содержимого файла
function readFileContent(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = (e) => reject(new Error('Ошибка чтения файла'));
        reader.readAsText(file);
    });
}

// Инициализация карточек результатов
function initializeResultCards(jobs) {
    resultsGrid.innerHTML = jobs.map(job => `
        <div class="result-card" id="card-${job.job_id}">
            <div class="result-info">
                <div class="result-name">${formatPromptName(job.prompt_name)}</div>
                <div class="result-meta">Обработка...</div>
            </div>
            <span class="result-status processing">В процессе</span>
            <button class="download-btn" disabled data-job-id="${job.job_id}">Скачать</button>
        </div>
    `).join('');
}

// Форматирование имени промпта
function formatPromptName(name) {
    return name
        .replace(/prompt_\d+_\d+_/, '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase());
}

// Начало polling статуса
function startPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
    
    // Проверяем сразу и затем каждые 3 секунды
    checkBatchStatus();
    pollingInterval = setInterval(checkBatchStatus, 3000);
}

// Проверка статуса батча
async function checkBatchStatus() {
    if (!currentBatchId) return;
    
    try {
        const response = await fetch(`/api/v1/ai_model/batch/${currentBatchId}`);
        
        if (!response.ok) {
            throw new Error('Ошибка при получении статуса');
        }
        
        const data = await response.json();
        updateProgress(data);
        
        // Если все завершено, останавливаем polling
        if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(pollingInterval);
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Получить документацию';
            
            if (data.status === 'completed') {
                downloadAllBtn.style.display = 'block';
            }
        }
        
    } catch (error) {
        console.error('Polling error:', error);
    }
}

// Обновление прогресса
function updateProgress(batchData) {
    const completed = batchData.completed_jobs || 0;
    const total = batchData.total_jobs || 0;
    const percentage = total > 0 ? (completed / total) * 100 : 0;
    
    progressStatus.textContent = `${completed} / ${total}`;
    progressBarFill.style.width = `${percentage}%`;
    
    // Обновляем статусы отдельных задач
    if (batchData.jobs) {
        batchData.jobs.forEach(updateJobCard);
    }
}

// Обновление карточки задачи
async function updateJobCard(job) {
    const card = document.getElementById(`card-${job.job_id}`);
    if (!card) return;
    
    const statusSpan = card.querySelector('.result-status');
    const downloadBtn = card.querySelector('.download-btn');
    const metaDiv = card.querySelector('.result-meta');
    
    // Обновляем статус
    statusSpan.className = 'result-status';
    
    if (job.status === 'finished') {
        statusSpan.classList.add('completed');
        statusSpan.textContent = 'Готово';
        downloadBtn.disabled = false;
        
        // Получаем детальную информацию
        try {
            const response = await fetch(`/api/v1/ai_model/jobs/${job.job_id}`);
            
            if (response.ok) {
                const details = await response.json();
                metaDiv.textContent = `Токенов: ${details.total_tokens || 0}`;
            }
        } catch (error) {
            console.error('Error fetching job details:', error);
        }
        
    } else if (job.status === 'failed') {
        statusSpan.classList.add('failed');
        statusSpan.textContent = 'Ошибка';
        metaDiv.textContent = job.error_message || 'Произошла ошибка';
        
    } else if (job.status === 'started') {
        statusSpan.classList.add('processing');
        statusSpan.textContent = 'Выполняется';
        metaDiv.textContent = 'Обработка AI модели...';
        
    } else {
        statusSpan.classList.add('processing');
        statusSpan.textContent = 'В очереди';
        metaDiv.textContent = 'Ожидание...';
    }
}

// Скачивание отдельного результата
resultsGrid.addEventListener('click', async (e) => {
    if (e.target.classList.contains('download-btn') && !e.target.disabled) {
        const jobId = e.target.dataset.jobId;
        await downloadResult(jobId);
    }
});

// Скачивание результата
async function downloadResult(jobId) {
    try {
        const response = await fetch(`/api/v1/ai_model/jobs/${jobId}`);
        
        if (!response.ok) {
            throw new Error('Ошибка при получении результата');
        }
        
        const data = await response.json();
        
        // Создаем и скачиваем файл
        const blob = new Blob([data.result_text], { type: 'text/markdown' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${data.prompt_name}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
    } catch (error) {
        console.error('Download error:', error);
        showError('Ошибка при скачивании файла');
    }
}

// Скачивание всех результатов
downloadAllBtn.addEventListener('click', async () => {
    if (!currentBatchId) return;
    
    downloadAllBtn.disabled = true;
    downloadAllBtn.innerHTML = 'Скачивание... <div class="spinner"></div>';
    
    try {
        const response = await fetch(`/api/v1/ai_model/batch/${currentBatchId}`);
        
        if (!response.ok) {
            throw new Error('Ошибка при получении результатов');
        }
        
        const batchData = await response.json();
        const completedJobs = batchData.jobs.filter(job => job.status === 'finished');
        
        // Скачиваем каждый результат
        for (const job of completedJobs) {
            await downloadResult(job.job_id);
            // Небольшая задержка между скачиваниями
            await new Promise(resolve => setTimeout(resolve, 300));
        }
        
        downloadAllBtn.disabled = false;
        downloadAllBtn.innerHTML = '📥 Скачать все результаты';
        
    } catch (error) {
        console.error('Download all error:', error);
        showError('Ошибка при скачивании результатов');
        downloadAllBtn.disabled = false;
        downloadAllBtn.innerHTML = '📥 Скачать все результаты';
    }
});

// Показ ошибки
function showError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.add('show');
}

// Скрытие ошибки
function hideError() {
    errorMessage.classList.remove('show');
}

