# -*- coding: utf-8 -*-
import json
import re
# from config import GEMINI_API_KEY (Hata diya gaya hai)

# --- HTML Template ---
# JavaScript <script> block se Gemini AI features hata diye gaye hain
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>H4R Test</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    
    <!-- MathJax (Math functions) ko comment out kar diya gaya hai -->
    <!--
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script>
    MathJax = {
      tex: {
        inlineMath: [['\\(', '\\)']], 
        displayMath: [['\\[', '\\]']] 
      },
      svg: {
        fontCache: 'global'
      }
    };
    </script>
    -->
    
    <style>
        :root {
            --background-light: #f8f9fa; --text-light: #212529; --card-bg-light: #ffffff;
            --primary-color: #4f46e5; --primary-hover: #4338ca; --border-light: #e5e7eb;
            --correct-bg: #dcfce7; --correct-text: #166534; --incorrect-bg: #fee2e2;
            --incorrect-text: #991b1b; --background-dark: #111827; --text-dark: #f9fafb;
            --card-bg-dark: #1f2937; --border-dark: #374151;
        }
        .light-mode { background-color: var(--background-light); color: var(--text-light); }
        .light-mode .card, .light-mode .modal-content { background-color: var(--card-bg-light); border: 1px solid var(--border-light); }
        .dark-mode { background-color: var(--background-dark); color: var(--text-dark); }
        .dark-mode .card, .dark-mode .modal-content { background-color: var(--card-bg-dark); border: 1px solid var(--border-dark); }
        
        .dark-mode .prose,
        .dark-mode .prose p, .dark-mode .prose li, .dark-mode .prose strong, .dark-mode .prose u,
        .dark-mode .prose h1, .dark-mode .prose h2, .dark-mode .prose h3, .dark-mode .prose th,
        .dark-mode .prose blockquote {
            color: var(--text-dark);
        }

        .dark-mode .prose img { border-radius: 0.5rem; }
        body { transition: background-color 0.3s, color 0.3s; }
        .hidden { display: none; }
        .option-radio { -webkit-appearance: none; -moz-appearance: none; appearance: none; border: 2px solid var(--border-light); border-radius: 50%; width: 20px; height: 20px; cursor: pointer; transition: all 0.2s; position: relative; }
        .dark-mode .option-radio { border-color: var(--border-dark); }
        .option-radio:checked { border-color: var(--primary-color); background-color: var(--primary-color); }
        .option-radio:checked::after { content: ''; display: block; width: 8px; height: 8px; background: white; border-radius: 50%; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); }
        .question-nav-btn { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; border-radius: 8px; font-weight: bold; transition: all 0.2s; }
        .status-not-answered { background-color: #e5e7eb; color: #374151; }
        .dark-mode .status-not-answered { background-color: #4b5563; color: #f9fafb; }
        .status-answered { background-color: #22c55e; color: white; }
        .status-marked { background-color: #8b5cf6; color: white; }
        .status-current { border: 2px solid var(--primary-color); }
        .review-status-correct { background-color: #22c55e; color: white; }
        .review-status-incorrect { background-color: #ef4444; color: white; }
        .review-status-marked { background-color: #8b5cf6; color: white; }
        .review-status-unanswered { background-color: #d1d5db; color: #1f2937; }
        .review-current { outline: 2px solid var(--primary-color); outline-offset: 2px; }
        
        .prose img { 
            max-width: 100%; 
            height: auto; 
            border-radius: 0.5rem;
            display: inline-block; 
            vertical-align: middle; 
        }
        
        .prose {
            overflow-wrap: break-word;
            word-wrap: break-word;
            word-break: break-all;
        }

        .force-black-text, .force-black-text * { color: #212529 !important; }

        .dark-mode ::-moz-selection { background: var(--primary-color); color: var(--text-dark); }
        .dark-mode ::selection { background: var(--primary-color); color: var(--text-dark); }

        .modal-lang-btn {
            width: 100%;
            padding: 0.75rem 1rem;
            border-radius: 0.5rem;
            font-weight: 600;
            transition: all 0.2s;
            border: 1px solid var(--border-light);
            text-align: center;
        }
        .dark-mode .modal-lang-btn {
            border-color: var(--border-dark);
        }
        .modal-lang-btn-active {
            background-color: var(--primary-color) !important;
            color: white !important;
            border-color: var(--primary-hover) !important;
        }
        .modal-lang-btn-inactive {
            background-color: #e5e7eb;
            color: #374151;
        }
        .dark-mode .modal-lang-btn-inactive {
            background-color: #374151;
            color: #f9fafb;
        }
    </style>
</head>
<body class="font-sans light-mode">
    
    <div id="welcome-screen" class="min-h-screen flex items-center justify-center p-4">
         <div class="card w-full max-w-lg p-6 sm:p-8 rounded-xl shadow-lg">
            <div class="text-center">
                <h1 class="text-2xl sm:text-3xl font-bold text-indigo-600">Welcome to H4R Test!</h1>
                <p class="mt-2 text-gray-600 dark:text-gray-400">Aapki mehnat hi aapki saflta ki kunji hai.</p>
            </div>
            <div class="border-t border-gray-200 dark:border-gray-700 mt-6 pt-6">
                <h2 class="text-xl font-bold mb-4 text-center">✨ Test Details ✨</h2>
                <div class="text-center">
                    <h3 class="text-xl sm:text-2xl font-bold">_TEST_NAME_</h3>
                    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">_TEST_SERIES_</p>
                </div>
                <div class="border-t border-b border-gray-200 dark:border-gray-700 py-4 my-6 text-left space-y-3">
                    <div class="flex justify-between items-center"><span class="font-semibold text-gray-700 dark:text-gray-300">📖 Section:</span><span class="text-gray-600 dark:text-gray-400 text-right">_SECTION_</span></div>
                    <div class="flex justify-between items-center"><span class="font-semibold text-gray-700 dark:text-gray-300">🧠 Subsection:</span><span class="text-gray-600 dark:text-gray-400 text-right">_SUBSECTION_</span></div>
                    <div class="flex justify-between items-center"><span class="font-semibold text-gray-700 dark:text-gray-300">✅ Correct:</span><span class="text-green-500 font-bold text-right notranslate">_CORRECT_MARKS_DISPLAY_</span></div>
                    <div class="flex justify-between items-center"><span class="font-semibold text-gray-700 dark:text-gray-300">❌ Incorrect:</span><span class="text-red-500 font-bold text-right notranslate">_INCORRECT_MARKS_DISPLAY_</span></div>
                </div>
                <div class="grid grid-cols-3 gap-4 text-center">
                    <div><p class="text-2xl font-bold text-indigo-500 notranslate">_QUESTIONS_</p><p class="text-xs text-gray-500 dark:text-gray-400">Questions</p></div>
                    <div><p class="text-2xl font-bold text-indigo-500 notranslate">_DURATION_</p><p class="text-xs text-gray-500 dark:text-gray-400">Duration</p></div>
                    <div><p class="text-2xl font-bold text-indigo-500 notranslate">_TOTAL_MARKS_</p><p class="text-xs text-gray-500 dark:text-gray-400">Marks</p></div>
                </div>
            </div>
            <div class="mt-8 space-y-4">
                 <button onclick="startQuiz()" class="w-full bg-indigo-600 text-white py-3 rounded-lg font-semibold hover:bg-indigo-700 transition duration-300 flex items-center justify-center gap-2"><i class="fas fa-play"></i> Start Test</button>
                 <!-- Telegram link ko hata dete hain, kyonki hum already Telegram mein hain
                 <a href="https://t.me/+LEGNpv9ucWMyZjkx" target="_blank" class="w-full bg-sky-500 text-white py-3 rounded-lg font-semibold hover:bg-sky-600 transition duration-300 flex items-center justify-center gap-2"><i class="fab fa-telegram-plane"></i> Join Telegram Channel</a>
                 -->
            </div>
        </div>
    </div>
    <div id="quiz-screen" class="hidden">
        <header class="card sticky top-0 z-10 p-3 sm:p-4 shadow-md rounded-none flex flex-col sm:flex-row justify-between items-center gap-2">
            <div class="text-center sm:text-left"><h1 id="quiz-title" class="text-lg sm:text-xl font-bold"></h1><div class="flex gap-4 text-xs sm:text-sm mt-1"><span><i class="fas fa-check text-green-500"></i> <span class="notranslate">_CORRECT_MARKS_DISPLAY_</span> Marks</span><span><i class="fas fa-times text-red-500"></i> <span class="notranslate">_INCORRECT_MARKS_DISPLAY_</span> Mark</span></div></div>
            <div class="flex items-center gap-2 sm:gap-4">
                <div id="timer" class="text-base sm:text-lg font-bold bg-blue-200 dark:bg-blue-700 px-3 py-1.5 sm:px-4 sm:py-2 rounded-lg notranslate"><i class="fas fa-clock"></i> <span id="time">00:00</span></div>
                <button id="lang-switch-btn" onclick="openLanguageModal()" class="bg-green-500 text-white px-3 py-1.5 sm:px-4 sm:py-2 rounded-lg hover:bg-green-600"><i class="fas fa-language"></i></button>
                <button id="theme-toggle" class="text-xl px-2"><i class="fas fa-moon"></i></button>
                <button onclick="openQuestionNav()" class="bg-indigo-500 text-white px-3 py-1.5 sm:px-4 sm:py-2 rounded-lg hover:bg-indigo-600"><i class="fas fa-th-large"></i></button>
                <button onclick="confirmSubmission()" class="bg-red-500 text-white px-3 py-1.5 sm:px-4 sm:py-2 rounded-lg hover:bg-red-600 font-semibold">Submit</button>
            </div>
        </header>
        <main class="p-4 md:p-8 max-w-6xl mx-auto"><div class="card p-4 sm:p-6 rounded-xl shadow-lg"><div class="flex justify-between items-center border-b pb-4 mb-4 dark:border-blue-600"><h2 class="text-lg sm:text-xl font-semibold">Question <span id="question-number" class="notranslate">1</span></h2></div><div id="question-container" class="prose max-w-none mb-6"></div><div id="options-container" class="space-y-4"></div></div><footer class="mt-6 flex flex-col sm:flex-row justify-between items-center gap-4"><div class="flex gap-4 w-full sm:w-auto"><button onclick="clearResponse()" class="flex-1 sm:flex-initial bg-blue-400 text-white px-4 py-2 sm:px-6 sm:py-3 rounded-lg hover:bg-blue-800 transition font-semibold"><i class="fas fa-trash"></i> Clear</button></div><div class="flex gap-4 w-full sm:w-auto"><button onclick="markForReview()" class="flex-1 sm:flex-initial bg-purple-500 text-white px-4 py-2 sm:px-6 sm:py-3 rounded-lg hover:bg-purple-600 transition font-semibold text-xs sm:text-sm">Mark & Next</button><button onclick="saveAndNext()" class="flex-1 sm:flex-initial bg-green-500 text-white px-4 py-2 sm:px-6 sm:py-3 rounded-lg hover:bg-green-600 transition font-semibold text-xs sm:text-sm">Save & Next</button></div></footer></main>
    </div>
    <div id="results-screen" class="hidden min-h-screen flex items-center justify-center p-4">
        <div class="card w-full max-w-lg text-center p-6 sm:p-8 rounded-xl shadow-lg"><h1 class="text-2xl sm:text-3xl font-bold mb-4">Your Results</h1><div class="text-4xl sm:text-5xl font-bold text-indigo-600 mb-6 notranslate"><span id="final-score">0</span> / <span id="total-score">0</span></div><div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8 text-center"><div><p class="text-2xl sm:text-3xl font-bold text-green-500 notranslate" id="correct-count">0</p><p class="text-xs sm:text-sm text-blue-200 dark:text-blue-600">Correct</p></div><div><p class="text-2xl sm:text-3xl font-bold text-red-500 notranslate" id="incorrect-count">0</p><p class="text-xs sm:text-sm text-blue-200 dark:text-blue-600">Incorrect</p></div><div><p class="text-2xl sm:text-3xl font-bold text-blue-500 notranslate" id="unanswered-count">0</p><p class="text-xs sm:text-sm text-blue-200 dark:text-blue-600">Unanswered</p></div><div><p class="text-2xl sm:text-3xl font-bold text-purple-500 notranslate" id="marked-count-result">0</p><p class="text-xs sm:text-sm text-blue-200 dark:text-blue-600">Marked</p></div></div><div class="flex flex-col sm:flex-row gap-4"><button onclick="reviewAnswers()" class="flex-1 bg-indigo-600 text-white py-3 rounded-lg font-semibold hover:bg-indigo-700 transition"><i class="fas fa-eye"></i> Review Answers</button><button onclick="restartQuiz()" class="flex-1 bg-blue-200 dark:bg-blue-600 py-3 rounded-lg font-semibold hover:bg-blue-300 dark:hover:bg-blue-700 transition">Close</button></div></div>
    </div>
    <div id="review-screen" class="hidden p-4 md:p-8 max-w-7xl mx-auto">
        <header class="card sticky top-0 z-10 p-3 sm:p-4 shadow-md flex justify-between items-center mb-8"><div id="review-question-counter" class="text-lg sm:text-xl font-bold"></div><div class="flex items-center gap-2 sm:gap-4">
        <button id="review-lang-switch-btn" onclick="openLanguageModal()" class="bg-green-500 text-white px-3 py-1.5 sm:px-4 sm:py-2 rounded-lg hover:bg-green-600"><i class="fas fa-language"></i></button>
        <button id="review-theme-toggle" class="text-xl px-2"><i class="fas fa-moon"></i></button><button onclick="backToResults()" class="bg-indigo-600 text-white px-4 py-2 sm:px-5 sm:py-2.5 rounded-lg hover:bg-indigo-700 font-semibold">Back</button></div></header><div class="flex flex-col lg:flex-row gap-8"><div class="w-full lg:w-3/4"><div id="review-container"></div><footer class="mt-8 flex justify-between items-center"><button id="prev-review-btn" onclick="prevReviewQuestion()" class="bg-indigo-500 text-white px-4 py-2 sm:px-6 sm:py-3 rounded-lg hover:bg-indigo-600 transition font-semibold flex items-center gap-2 disabled:opacity-50"><i class="fas fa-chevron-left"></i> Previous</button><button id="next-review-btn" onclick="nextReviewQuestion()" class="bg-indigo-500 text-white px-4 py-2 sm:px-6 sm:py-3 rounded-lg hover:bg-indigo-6D00 transition font-semibold flex items-center gap-2 disabled:opacity-50">Next <i class="fas fa-chevron-right"></i></button></footer></div><aside class="w-full lg:w-1/4"><div class="card p-4 rounded-xl shadow-lg"><h3 class="font-bold mb-4">Question Palette</h3><div id="review-palette-grid" class="grid grid-cols-5 sm:grid-cols-6 md:grid-cols-4 lg:grid-cols-5 gap-2"></div><div class="mt-4 space-y-2 text-xs"><div class="flex items-center gap-2"><div class="w-4 h-4 rounded-sm review-status-correct"></div> Correct</div><div class="flex items-center gap-2"><div class="w-4 h-4 rounded-sm review-status-incorrect"></div> Incorrect</div><div class="flex items-center gap-2"><div class="w-4 h-4 rounded-sm review-status-unanswered"></div> Unanswered</div><div class="flex items-center gap-2"><div class="w-4 h-4 rounded-sm review-status-marked"></div> Marked</div></div></div></aside></div>
    </div>
    <div id="question-nav-modal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"><div class="modal-content w-full max-w-2xl p-4 sm:p-6 rounded-xl shadow-lg"><div class="flex justify-between items-center mb-4"><h2 class="text-2xl font-bold">Questions</h2><button onclick="closeQuestionNav()" class="text-2xl">&times;</button></div><div class="flex flex-wrap gap-4 items-center mb-4 text-xs"><div class="flex items-center gap-2"><div class="w-4 h-4 rounded-full bg-green-500"></div>Answered</div><div class="flex items-center gap-2"><div class="w-4 h-4 rounded-full bg-blue-300 dark:bg-blue-600"></div>Not Answered</div><div class="flex items-center gap-2"><div class="w-4 h-4 rounded-full bg-purple-500"></div>Marked</div><div class="flex items-center gap-2"><div class="w-4 h-4 rounded-full border-2 border-indigo-600"></div>Current</div></div><div id="question-grid" class="grid grid-cols-5 sm:grid-cols-8 md:grid-cols-10 gap-3"></div></div></div>
    <div id="confirm-submit-modal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"><div class="modal-content w-full max-w-md text-center p-6 sm:p-8 rounded-xl shadow-lg"><h2 class="text-2xl font-bold mb-4">H4R Test</h2><p class="mb-6">You have <span id="unanswered-modal-count" class="font-bold">0</span> unanswered questions. Are you sure you want to submit?</p><div class="flex gap-4"><button onclick="closeConfirmSubmission()" class="flex-1 bg-blue-200 dark:bg-blue-600 py-3 rounded-lg font-semibold hover:bg-blue-300 dark:hover:bg-blue-700 transition">CANCEL</button><button onclick="submitQuiz()" class="flex-1 bg-red-500 text-white py-3 rounded-lg font-semibold hover:bg-red-600 transition">OK</button></div></div></div>
    <div id="language-modal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
        <div class="modal-content w-full max-w-xs p-4 sm:p-6 rounded-xl shadow-lg">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-2xl font-bold">Choose Language</h2>
                <button onclick="closeLanguageModal()" class="text-2xl">&times;</button>
            </div>
            <div id="language-options-container" class="space-y-3 max-h-72 overflow-y-auto">
            </div>
        </div>
    </div>

    <script>
        // --- DATA ---
        const quizData = /* QUIZ_DATA_PLACEHOLDER */;
        
        // --- GEMINI API KEY (Hata diya gaya hai) ---
        
        // --- CONFIG ---
        let timeRemaining = _TIMER_SECONDS_; 
        let CORRECT_MARKS = _JS_CORRECT_MARKS_VALUE_; 
        let INCORRECT_MARKS = _JS_INCORRECT_MARKS_VALUE_;
        const langDisplayNames = { 'en': 'Eng', 'hn': 'हिन्दी', 'hi': 'हिन्दी' }; 
        
        // --- STATE ---
        let currentQuestionIndex = 0, currentReviewIndex = 0;
        let userAnswers = [], questionStatus = [];
        let score = 0, timer;
        let currentLanguage = 'en'; 

        // --- ELEMENTS ---
        const welcomeScreen = document.getElementById('welcome-screen'); 
        const quizScreen = document.getElementById('quiz-screen'); 
        const resultsScreen = document.getElementById('results-screen'); 
        const reviewScreen = document.getElementById('review-screen'); 
        const quizTitleEl = document.getElementById('quiz-title'); 
        const timeEl = document.getElementById('time'); 
        const questionNumberEl = document.getElementById('question-number'); 
        const questionContainer = document.getElementById('question-container'); 
        const optionsContainer = document.getElementById('options-container');

        // --- UTILITY FUNCTIONS ---
        
        function decodeHtml(html) {
            if (!html) return "";
            var txt = document.createElement("textarea");
            txt.innerHTML = html;
            let decodedHtml = txt.value;
            // Fix relative URLs
            decodedHtml = decodedHtml.replace(/src=(["'])\/\//g, 'src=$1https://');
            decodedHtml = decodedHtml.replace(/src=(["'])\/([^\/])/g, 'src=$1https://testbook.com/$2');
            return decodedHtml;
        }

        function getLocalizedContent(contentObject) {
            if (!contentObject) return "";
            if (contentObject[currentLanguage]) return contentObject[currentLanguage];
            if (contentObject['en']) return contentObject['en'];
            const firstLang = Object.keys(contentObject)[0];
            return contentObject[firstLang] || "";
        }
        
        // --- LANGUAGE SWITCHER LOGIC ---
        function openLanguageModal() { document.getElementById('language-modal').classList.remove('hidden'); }
        function closeLanguageModal() { document.getElementById('language-modal').classList.add('hidden'); }
        function initLanguageSelector() {
            const languages = quizData.available_languages || [];
            const selectorContainer = document.getElementById('language-options-container'); 
            selectorContainer.innerHTML = ''; 
            if (languages.length > 1) {
                languages.forEach(langCode => {
                    const btn = document.createElement('button');
                    btn.id = `lang-btn-${langCode}`;
                    btn.textContent = langDisplayNames[langCode] || langCode.toUpperCase();
                    btn.className = 'modal-lang-btn';
                    btn.onclick = () => changeLanguage(langCode);
                    selectorContainer.appendChild(btn);
                });
                currentLanguage = languages.includes('en') ? 'en' : languages[0];
                updateLanguageButtons();
            } else {
                const langBtn = document.getElementById('lang-switch-btn');
                const reviewLangBtn = document.getElementById('review-lang-switch-btn');
                if (langBtn) langBtn.classList.add('hidden');
                if (reviewLangBtn) reviewLangBtn.classList.add('hidden');
            }
        }
        function updateLanguageButtons() {
            document.querySelectorAll('#language-options-container .modal-lang-btn').forEach(btn => {
                const langCode = btn.id.replace('lang-btn-', '');
                if (langCode === currentLanguage) {
                    btn.classList.add('modal-lang-btn-active');
                    btn.classList.remove('modal-lang-btn-inactive');
                } else {
                    btn.classList.add('modal-lang-btn-inactive');
                    btn.classList.remove('modal-lang-btn-active');
                }
            });
        }
        function changeLanguage(langCode) {
            currentLanguage = langCode;
            updateLanguageButtons(); 
            if (!quizScreen.classList.contains('hidden')) {
                loadQuestion(currentQuestionIndex);
            } else if (!reviewScreen.classList.contains('hidden')) {
                loadReviewQuestion(currentReviewIndex);
            }
            closeLanguageModal(); 
        }

        // --- QUIZ LIFECYCLE ---
        function initQuiz() { 
            quizTitleEl.textContent = quizData.title; 
            userAnswers = new Array(quizData.questions.length).fill(null); 
            questionStatus = new Array(quizData.questions.length).fill('not-answered'); 
            initLanguageSelector(); 
        }
        function startQuiz() { 
            welcomeScreen.classList.add('hidden'); 
            quizScreen.classList.remove('hidden'); 
            initQuiz(); 
            loadQuestion(0); 
            startTimer(); 
        }
        function restartQuiz() { 
            // 'Close' button ab page ko reload karega
            window.location.reload();
        }
        function startTimer() { 
            clearInterval(timer); 
            timer = setInterval(() => { 
                timeRemaining--; 
                const minutes = Math.floor(timeRemaining / 60).toString().padStart(2, '0'); 
                const seconds = (timeRemaining % 60).toString().padStart(2, '0'); 
                timeEl.textContent = `${minutes}:${seconds}`; 
                if (timeRemaining <= 0) { 
                    clearInterval(timer); 
                    submitQuiz(); 
                } 
            }, 1000); 
        }

        // --- QUESTION LOADING ---
        function loadQuestion(index) {
            if (index < 0 || index >= quizData.questions.length) return; 
            currentQuestionIndex = index; 
            questionStatus[index] = 'current'; 
            
            const question = quizData.questions[index];
            const questionText = getLocalizedContent(question.content);
            const questionOptions = getLocalizedContent(question.options);

            questionNumberEl.textContent = index + 1; 
            questionContainer.innerHTML = decodeHtml(questionText); 
            optionsContainer.innerHTML = ''; 
            
            if (Array.isArray(questionOptions)) {
                questionOptions.forEach((option, i) => { 
                    const isSelected = userAnswers[index] === i; 
                    const optionId = `option-${index}-${i}`; 
                    const optionHTML = `<label for="${optionId}" class="flex items-start sm:items-center gap-4 p-4 border rounded-lg cursor-pointer transition hover:border-indigo-500 dark:border-blue-600 dark:hover:border-indigo-500 ${isSelected ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-900/50' : ''}"><input type="radio" id="${optionId}" name="option" value="${i}" class="option-radio mt-1 sm:mt-0" onchange="selectOption(${i})" ${isSelected ? 'checked' : ''}><div class="prose max-w-none flex-1 overflow-x-auto">${decodeHtml(option.text)}</div></label>`; 
                    optionsContainer.insertAdjacentHTML('beforeend', optionHTML); 
                });
            } else {
                 optionsContainer.innerHTML = "<p>Error: Options not available in selected language.</p>";
            }

            /* MathJax call ko comment out kar diya gaya hai */
        }
        
        // --- NAVIGATION & SUBMISSION ---
        function selectOption(optionIndex) { 
            userAnswers[currentQuestionIndex] = optionIndex; 
            loadQuestion(currentQuestionIndex); 
        }
        function clearResponse() { 
            userAnswers[currentQuestionIndex] = null; 
            loadQuestion(currentQuestionIndex); 
        }
        function saveAndNext() { 
            questionStatus[currentQuestionIndex] = userAnswers[currentQuestionIndex] !== null ? 'answered' : 'not-answered'; 
            if (currentQuestionIndex < quizData.questions.length - 1) { 
                loadQuestion(currentQuestionIndex + 1); 
            } else { 
                confirmSubmission(); 
            } 
        }
        function markForReview() { 
            questionStatus[currentQuestionIndex] = 'marked'; 
            if (currentQuestionIndex < quizData.questions.length - 1) { 
                loadQuestion(currentQuestionIndex + 1); 
            } else { 
                confirmSubmission(); 
            } 
        }
        function confirmSubmission() { 
            document.getElementById('unanswered-modal-count').textContent = userAnswers.filter(ans => ans === null).length; 
            document.getElementById('confirm-submit-modal').classList.remove('hidden'); 
        }
        function closeConfirmSubmission() { 
            document.getElementById('confirm-submit-modal').classList.add('hidden'); 
        }
        function submitQuiz() { 
            closeConfirmSubmission(); 
            clearInterval(timer); 
            calculateScore(); 
            showResults(); 
            
            /* Firebase 'addTestAttempt' ko yahan se hata diya gaya hai, kyonki yeh 'file://' context mein kaam nahi karega */
        }
        
        // --- RESULTS & SCORE ---
        function calculateScore() { 
            score = 0; 
            quizData.questions.forEach((q, index) => { 
                const userAnswerIndex = userAnswers[index]; 
                if (userAnswerIndex !== null) { 
                    const options = q.options['en'] || q.options[Object.keys(q.options)[0]];
                    if (options && options[userAnswerIndex] && options[userAnswerIndex].is_correct) { 
                        score += CORRECT_MARKS; 
                    } else { 
                        score += INCORRECT_MARKS; 
                    } 
                } 
            }); 
        }
        function showResults() { 
            quizScreen.classList.add('hidden'); 
            resultsScreen.classList.remove('hidden'); 
            
            const getCheckOptions = (q) => q.options['en'] || q.options[Object.keys(q.options)[0]];

            const correctCount = userAnswers.filter((ans, i) => ans !== null && getCheckOptions(quizData.questions[i])[ans].is_correct).length; 
            const incorrectCount = userAnswers.filter((ans, i) => ans !== null && !getCheckOptions(quizData.questions[i])[ans].is_correct).length; 
            const unansweredCount = userAnswers.filter(ans => ans === null).length; 
            const markedCount = questionStatus.filter(status => status === 'marked').length; 
            
            document.getElementById('final-score').textContent = score.toFixed(2); 
            document.getElementById('total-score').textContent = (quizData.questions.length * CORRECT_MARKS).toFixed(2); 
            document.getElementById('correct-count').textContent = correctCount; 
            document.getElementById('incorrect-count').textContent = incorrectCount; 
            document.getElementById('unanswered-count').textContent = unansweredCount; 
            document.getElementById('marked-count-result').textContent = markedCount; 
        }
        
        // --- REVIEW ANSWERS ---
        function reviewAnswers() { 
            resultsScreen.classList.add('hidden'); 
            reviewScreen.classList.remove('hidden'); 
            currentReviewIndex = 0; 
            loadReviewQuestion(currentReviewIndex); 
            populateReviewPalette(); 
        }
        function loadReviewQuestion(index) { 
            try { 
                currentReviewIndex = index; 
                const reviewContainer = document.getElementById('review-container'); 
                reviewContainer.innerHTML = ''; 
                if (index < 0 || index >= quizData.questions.length) return; 
                
                const q = quizData.questions[index]; 
                if (!q || !q.options || !q.content) { 
                    reviewContainer.innerHTML = "<p>Error: Question data is missing or corrupt.</p>"; 
                    return; 
                }

                const q_content = getLocalizedContent(q.content);
                const q_options = getLocalizedContent(q.options);
                const q_solution = getLocalizedContent(q.solution);

                const userAnswerIndex = userAnswers[index]; 
                let correctOptionIndex = -1; 
                
                if (!Array.isArray(q_options)) {
                     reviewContainer.innerHTML = "<p>Error: Review options not available in selected language.</p>";
                     return;
                }

                q_options.forEach((opt, i) => { 
                    if (opt.is_correct) correctOptionIndex = i; 
                }); 
                
                let optionsHTML = ''; 
                q_options.forEach((opt, i) => { 
                    let optionClass = '', icon = ''; 
                    
                    if (i === correctOptionIndex) { 
                        optionClass = 'bg-green-100 dark:bg-green-900/50 border-green-500 force-black-text'; 
                        icon = '<i class="fas fa-check-circle text-green-600"></i>';
                    } else if (i === userAnswerIndex) { 
                        optionClass = 'bg-red-100 dark:bg-red-900/50 border-red-500'; 
                        icon = '<i class="fas fa-times-circle text-red-600"></i>'; 
                    } 
                const reviewCard = `<div class="card p-4 sm:p-6 rounded-xl shadow-md"><p class="font-semibold mb-2">Question <span class="notranslate">${index + 1}</span></p><div class="prose max-w-none mb-4 overflow-x-auto">${decodeHtml(q_content || "Question text not available.")}</div><div class="space-y-3 mb-4">${optionsHTML}</div><div class="mt-4 p-4 bg-gray-100 dark:bg-gray-800 rounded-lg border-t-4 border-green-500"><h4 class="font-bold mb-2 text-green-700 dark:text-green-400">Solution</h4><div class="prose max-w-none force-black-text overflow-x-auto">${decodeHtml(q_solution || "Solution not available.")}</div></div>
                
                <!-- AI Explanation feature yahan se hata diya gaya hai -->
                
                </div>`; 
                reviewContainer.insertAdjacentHTML('beforeend', reviewCard); 
                
                document.getElementById('review-question-counter').textContent = `Question ${index + 1} of ${quizData.questions.length}`; 
                document.getElementById('prev-review-btn').disabled = index === 0; 
                document.getElementById('next-review-btn').disabled = index === quizData.questions.length - 1; 
                updatePaletteHighlight(); 

            } catch (e) { 
                console.error("Error loading review question:", e); 
                document.getElementById('review-container').innerHTML = `<p class="text-red-500">Sorry, there was an error loading this question's review.</p>`; 
            } 
        }

        // --- GEMINI EXPLANATION (Functions hata diye gaye hain) ---
        
        // --- REVIEW PALETTE & NAVIGATION ---
        function populateReviewPalette() { 
            const paletteGrid = document.getElementById('review-palette-grid'); 
            paletteGrid.innerHTML = ''; 
            const getCheckOptions = (q) => q.options['en'] || q.options[Object.keys(q.options)[0]];
            quizData.questions.forEach((q, i) => { 
                const btn = document.createElement('button'); 
                btn.textContent = i + 1; 
                btn.id = `review-btn-${i}`; 
                btn.className = 'question-nav-btn notranslate'; 
                const userAnswer = userAnswers[i];
                const checkOptions = getCheckOptions(q);
                const isCorrect = userAnswer !== null && checkOptions && checkOptions[userAnswer] && checkOptions[userAnswer].is_correct; 
                const status = questionStatus[i]; 
                if (isCorrect) { btn.classList.add('review-status-correct'); } else if (userAnswer !== null && !isCorrect) { btn.classList.add('review-status-incorrect'); } else if (status === 'marked') { btn.classList.add('review-status-marked'); } else { btn.classList.add('review-status-unanswered'); } 
                btn.onclick = () => jumpToReviewQuestion(i); 
                paletteGrid.appendChild(btn); 
            }); 
            updatePaletteHighlight(); 
        }
        function updatePaletteHighlight() { 
            document.querySelectorAll('#review-palette-grid .question-nav-btn').forEach(btn => { btn.classList.remove('review-current'); }); 
            const currentBtn = document.getElementById(`review-btn-${currentReviewIndex}`); 
            if (currentBtn) { currentBtn.classList.add('review-current'); } 
        }
        function jumpToReviewQuestion(index) { loadReviewQuestion(index); }
        function nextReviewQuestion() { if (currentReviewIndex < quizData.questions.length - 1) { loadReviewQuestion(currentReviewIndex + 1); } }
        function prevReviewQuestion() { if (currentReviewIndex > 0) { loadReviewQuestion(currentReviewIndex - 1); } }
        function backToResults() { reviewScreen.classList.add('hidden'); resultsScreen.classList.remove('hidden'); }
        
        // --- QUESTION NAV MODAL ---
        function openQuestionNav() { 
            const grid = document.getElementById('question-grid'); grid.innerHTML = ''; quizData.questions.forEach((_, i) => { let statusClass = 'status-not-answered'; if (questionStatus[i] === 'answered') statusClass = 'status-answered'; if (questionStatus[i] === 'marked') statusClass = 'status-marked'; const isCurrent = i === currentQuestionIndex ? 'status-current' : ''; const btn = document.createElement('button'); btn.textContent = i + 1; btn.className = `question-nav-btn ${statusClass} ${isCurrent} notranslate`; btn.onclick = () => { if (userAnswers[currentQuestionIndex] !== null && questionStatus[currentQuestionIndex] !== 'marked') { questionStatus[currentQuestionIndex] = 'answered'; } else if (questionStatus[currentQuestionIndex] !== 'marked') { questionStatus[currentQuestionIndex] = 'not-answered'; } loadQuestion(i); closeQuestionNav(); }; grid.appendChild(btn); }); document.getElementById('question-nav-modal').classList.remove('hidden'); 
        }
        function closeQuestionNav() { document.getElementById('question-nav-modal').classList.add('hidden'); }
        
        // --- THEME TOGGLE ---
        const themeToggles = [document.getElementById('theme-toggle'), document.getElementById('review-theme-toggle')]; 
        const body = document.body;
        function applyThemeIcons() { 
            const isDarkMode = body.classList.contains('dark-mode'); 
            themeToggles.forEach(toggle => { 
                if (toggle) { 
                    const themeIcon = toggle.querySelector('i'); 
                    if (isDarkMode) { 
                        themeIcon.classList.remove('fa-moon'); themeIcon.classList.add('fa-sun'); 
                    } else { 
                        themeIcon.classList.remove('fa-sun'); themeIcon.classList.add('fa-moon'); 
                    } 
                } 
            }); 
        }
        themeToggles.forEach(toggle => { 
            if (toggle) { 
                toggle.addEventListener('click', () => { 
                    body.classList.toggle('light-mode'); 
                    body.classList.toggle('dark-mode'); 
                    applyThemeIcons(); 
                }); 
            } 
        });
        
        // --- INITIALIZATION ---
        document.addEventListener('DOMContentLoaded', () => { 
            try { 
                if (!quizData || !quizData.questions || quizData.questions.length === 0) { 
                    throw new Error("Invalid quiz data"); 
                } 
                applyThemeIcons(); 
            } catch (e) { 
                console.error("Initialization Error:", e); 
                const welcomeContent = document.querySelector('#welcome-screen .card'); 
                if(welcomeContent){ 
                    welcomeContent.innerHTML = `<div class="text-center"><h1 class="text-2xl font-bold text-red-600">Error</h1><p class="mt-4">Is file mein quiz data nahi mil saka ya format galat hai. ${e.message}</p></div>`; 
                } 
            } 
        });
    </script>
</body>
</html>
"""

def generate_html(quiz_data: dict, details: dict) -> str:
    """
    JSON data aur test details se ek complete HTML string generate karta hai.
    """
    processed_content_str = json.dumps(quiz_data, ensure_ascii=False)
    
    final_html = HTML_TEMPLATE.replace('/* QUIZ_DATA_PLACEHOLDER */', processed_content_str)

    duration_in_seconds = 1800  # Default 30 minutes
    duration_str = details.get('Duration', '30 minutes')
    if 'minutes' in duration_str:
        try:
            minutes = int(duration_str.split()[0])
            duration_in_seconds = minutes * 60
        except (ValueError, IndexError):
            duration_in_seconds = 1800 # Fallback

    correct_marks_str = details.get('Correct', '+3')
    incorrect_marks_str = details.get('Incorrect', '-1')
    
    correct_match = re.search(r'([+-]?\d+\.?\d*)', str(correct_marks_str))
    incorrect_match = re.search(r'([+-]?\d+\.?\d*)', str(incorrect_marks_str))
    
    correct_marks_js = float(correct_match.group(1)) if correct_match else 3.0
    incorrect_marks_js = float(incorrect_match.group(1)) if incorrect_match else -1.0

    replacements = {
        '_TEST_NAME_': details.get('Test Name', quiz_data.get('title', 'Online Mock Test')),
        '_TEST_SERIES_': details.get('Test Series', ''),
        '_SECTION_': details.get('Section', 'N/A'),
        '_SUBSECTION_': details.get('Subsection', 'N/A'),
        '_QUESTIONS_': details.get('Questions', str(len(quiz_data.get("questions", [])))),
        '_DURATION_': details.get('Duration', '30 minutes'),
        '_TOTAL_MARKS_': details.get('Total Marks', 'N/A'),
        '_TIMER_SECONDS_': str(duration_in_seconds),
        '_CORRECT_MARKS_DISPLAY_': str(correct_marks_str),
        '_INCORRECT_MARKS_DISPLAY_': str(incorrect_marks_str),
        '_JS_CORRECT_MARKS_VALUE_': str(correct_marks_js),
        '_JS_INCORRECT_MARKS_VALUE_': str(incorrect_marks_js),
        # GEMINI_API_KEY placeholder yahan se hata diya gaya hai
    }

    for placeholder, value in replacements.items():
        final_html = final_html.replace(placeholder, str(value))

    return final_html

