/**
 * Kadai Khata - Mobile-First Single Page Application
 * Pure Vanilla JavaScript - No build step, no external dependencies.
 * XSS-safe: all user text is escaped or inserted via textContent.
 */

(function () {
    "use strict";

    // --- i18n Dictionary (Genuine Tamil Script & English) ---
    const I18N = {
        en: {
            appTitle: "Kadai Khata",
            langBtnLabel: "தமிழ்",
            totalOutstanding: "Total Outstanding",
            customersCount: "{n} Customers",
            summaryHint: "Net credit owed across all customers",
            searchPlaceholder: "Search by customer name or phone...",
            customerLedger: "Customer Accounts",
            noCustomersFound: "No customer records found",
            noCustomersHint: "Type a transaction in the input bar below to create one.",
            confirmDraftsTitle: "Review Draft Entries",
            nothingSavedHint: "Nothing is saved to the ledger until you click Confirm.",
            confirmAll: "Confirm All",
            closeDrafts: "Close",
            clarificationTitle: "Clarification Needed:",
            back: "Back",
            outstandingBalance: "Current Balance",
            sendReminder: "Draft Reminder",
            transactionTimeline: "Transaction Timeline & Audit",
            noEntriesYet: "No transactions yet",
            noEntriesHint: "Add udhaar or varavu below to start tracking.",
            comingSoon: "Coming soon",
            sentencePlaceholder: "Type: 'Ravi 500 udhaar kuduthen'...",
            send: "Send",
            reminderTitle: "Payment Reminder",
            reminderLanguage: "Language",
            reminderTone: "Tone",
            toneSoft: "Soft / Friendly",
            toneFirm: "Firm / Clear",
            generateDraft: "Generate Reminder",
            verifiedAmount: "Verified amount",
            openWhatsApp: "Open in WhatsApp",
            copyMessage: "Copy Message",
            copied: "Copied!",
            reminderPrivacyNotice: "The app never sends anything itself. You review and send manually.",
            matchesCustomer: "Matches existing customer",
            newCustomer: "New customer",
            udhaar: "Udhaar (Credit)",
            varavu: "Varavu (Payment)",
            confirm: "Confirm",
            reject: "Reject",
            reverseEntry: "Reverse Entry",
            reversedBadge: "Reversed",
            reversalEntryBadge: "Reversal Record",
            reversalPrompt: "Reason for reversal (optional):",
            daysAgo: "{n}d ago",
            today: "Today",
            parsingSentence: "Understanding Tanglish transaction...",
            errorNetwork: "Network request failed. Please check your connection.",
            confirmSuccess: "Transaction confirmed and recorded.",
            rejectSuccess: "Draft discarded.",
            reversalSuccess: "Entry successfully reversed.",
            chooseCandidate: "Multiple matching customers found. Choose one:",
            tabLedger: "Ledger",
            tabCollections: "Collections",
            askTitle: "Ask Balance",
            askPlaceholder: "Ravi evlo baaki?...",
            askBtn: "Ask",
            collectionsTitle: "Daily Collections Review",
            collectionsSubtitle: "AI proposes who to remind today. Read-only review.",
            runCollectionsReview: "Run today's review",
            runningReview: "Analyzing ledger...",
            noPlanYet: "No collections review yet",
            noPlanHint: "Click 'Run today's review' above to analyze outstanding balances and generate verified proposals.",
            agentTrace: "Agent Execution Trace",
            chainValid: "Chain valid",
            chainInvalid: "Chain broken",
            actionRemindNow: "Remind Now",
            actionWait: "Wait",
            actionCallPersonally: "Call Personally",
            toneSoftBadge: "Soft",
            toneFirmBadge: "Firm",
            verifiedBadge: "Verified",
            unverifiedBadge: "Unverified",
            draftReminderBtn: "Draft Reminder",
            skipBtn: "Skip",
            evidenceTitle: "Evidence:",
            failedChecksTitle: "Failed checks:",
            runReviewSuccess: "Collections review completed.",
            photoPrivacyNotice: "Photo is processed in memory and not stored. Use test pages only in demos.",
            columnTotalCheck: "Per-Column Total Check",
            totalUdhaarLabel: "Udhaar / கடன் (Credit)",
            totalJamaLabel: "Jama / வரவு (Payment)",
            skippedRowsTitle: "Skipped Rows (Not Drafted)",
            photoAckText: "I acknowledge column total differences and skipped rows.",
            photoTotalMatched: "Totals match",
            photoTotalMismatch: "Totals mismatch",
            uploadingPhoto: "Processing photo (downscaling & extracting rows)...",
            useLatinName: "Use English",
            useTamilName: "Use Tamil",
            tryThese: "Try these:",
            trySampleNotebook: "Try a sample notebook page",
            howItWorks: "How it works"
        },
        ta: {
            appTitle: "கடை கணக்கு",
            langBtnLabel: "English",
            totalOutstanding: "மொத்த பாக்கி",
            customersCount: "{n} வாடிக்கையாளர்கள்",
            summaryHint: "அனைத்து வாடிக்கையாளர் மொத்த கடன்",
            searchPlaceholder: "வாடிக்கையாளர் பெயர் அல்லது போன் எண் தேடுக...",
            customerLedger: "வாடிக்கையாளர் கணக்குகள்",
            noCustomersFound: "வாடிக்கையாளர் பதிவுகள் எதுவும் இல்லை",
            noCustomersHint: "கீழே உள்ள உள்ளீட்டுப் பட்டியில் பதிவை உள்ளிடவும்.",
            confirmDraftsTitle: "வரைவு உள்ளீடுகளை சரிபார்க்கவும்",
            nothingSavedHint: "உறுதி செய்யும் வரை கணக்கில் எதுவும் சேமிக்கப்படாது.",
            confirmAll: "அனைத்தும் உறுதி செய்",
            closeDrafts: "மூடு",
            clarificationTitle: "விளக்கம் தேவை:",
            back: "பின்செல்",
            outstandingBalance: "தற்போதைய பாக்கி",
            sendReminder: "நினைவூட்டல் உருவாக்கு",
            transactionTimeline: "பரிவர்த்தனை வரலாறு & தணிக்கை",
            noEntriesYet: "பரிவர்த்தனைகள் எதுவும் இல்லை",
            noEntriesHint: "கீழே உள்ளீட்டை சேர்த்து கணக்கைத் தொடங்குங்கள்.",
            comingSoon: "விரைவில்",
            sentencePlaceholder: "எழுதுக: 'ரவி 500 உதார் குடுத்தேன்'...",
            send: "பதிவு செய்",
            reminderTitle: "கடன் நினைவூட்டல்",
            reminderLanguage: "மொழி",
            reminderTone: "தொனி",
            toneSoft: "பணிவான / நட்பு",
            toneFirm: "தெளிவான / கண்டிப்பான",
            generateDraft: "நினைவூட்டல் உருவாக்கு",
            verifiedAmount: "சரிபார்க்கப்பட்ட தொகை",
            openWhatsApp: "வாட்ஸ்அப்பில் திற",
            copyMessage: "செய்தியை நகலெடு",
            copied: "நகலெடுக்கப்பட்டது!",
            reminderPrivacyNotice: "செயலி எதையும் தானாக அனுப்பாது. சரிபார்த்து நீங்களே அனுப்ப வேண்டும்.",
            matchesCustomer: "பழைய வாடிக்கையாளர்",
            newCustomer: "புதிய வாடிக்கையாளர்",
            udhaar: "உதார் (கடன்)",
            varavu: "வரவு (பணம்)",
            confirm: "உறுதி செய்",
            reject: "நிராகரி",
            reverseEntry: "ரத்து செய்",
            reversedBadge: "ரத்து செய்யப்பட்டது",
            reversalEntryBadge: "ரத்து பதிவு",
            reversalPrompt: "ரத்து செய்வதற்கான காரணம் (விருப்பத்தேர்வு):",
            daysAgo: "{n} நாட்களுக்கு முன்",
            today: "இன்று",
            parsingSentence: "உள்ளீடு புரிந்து கொள்ளப்படுகிறது...",
            errorNetwork: "இணைய இணைப்பு தோல்வியடைந்தது.",
            confirmSuccess: "பதிவு உறுதி செய்யப்பட்டு சேமிக்கப்பட்டது.",
            rejectSuccess: "வரைவு நிராகரிக்கப்பட்டது.",
            reversalSuccess: "பதிவு வெற்றிகரமாக ரத்து செய்யப்பட்டது.",
            chooseCandidate: "பொருத்தமான வாடிக்கையாளரை தேர்ந்தெடுக்கவும்:",
            tabLedger: "கணக்கு",
            tabCollections: "வசூல்",
            askTitle: "கணக்கு கேள்",
            askPlaceholder: "ரவி எவ்ளோ பாக்கி?...",
            askBtn: "கேள்",
            collectionsTitle: "தினசரி வசூல் மதிப்பாய்வு",
            collectionsSubtitle: "யாரை நினைவூட்ட வேண்டும் என்பதை AI பரிந்துரைக்கும். வாசிப்பு மட்டுமே.",
            runCollectionsReview: "இன்றைய மதிப்பாய்வை தொடங்கு",
            runningReview: "கணக்குகள் பகுப்பாய்வு செய்யப்படுகின்றன...",
            noPlanYet: "மதிப்பாய்வு இன்னும் செய்யப்படவில்லை",
            noPlanHint: "'இன்றைய மதிப்பாய்வை தொடங்கு' பட்டனை அழுத்தி பாக்கி விபரங்களை பகுப்பாய்வு செய்யவும்.",
            agentTrace: "முகவர் செயல்பாட்டு தணிக்கை",
            chainValid: "சங்கிலி உறுதி",
            chainInvalid: "சங்கிலி தவறு",
            actionRemindNow: "நினைவூட்டு",
            actionWait: "காத்திரு",
            actionCallPersonally: "நேரில் அழை",
            toneSoftBadge: "பணிவான தொனி",
            toneFirmBadge: "கண்டிப்பான தொனி",
            verifiedBadge: "சரிபார்க்கப்பட்டது",
            unverifiedBadge: "சரிபார்க்கப்படவில்லை",
            draftReminderBtn: "நினைவூட்டல் உருவாக்கு",
            skipBtn: "தவிர்",
            evidenceTitle: "ஆதாரம்:",
            failedChecksTitle: "தோல்வியடைந்த சோதனைகள்:",
            runReviewSuccess: "வசூல் மதிப்பாய்வு முடிந்தது.",
            photoPrivacyNotice: "புகைப்படம் நினைவகத்தில் மட்டுமே செயலாக்கப்படுகிறது, சேமிக்கப்படுவதில்லை. டெமோக்களில் சோதனை பக்கங்களை மட்டுமே பயன்படுத்தவும்.",
            columnTotalCheck: "நிரல் வாரியான மொத்த சரிபார்ப்பு",
            totalUdhaarLabel: "கடன் (Udhaar)",
            totalJamaLabel: "வரவு (Jama)",
            skippedRowsTitle: "தவிர்க்கப்பட்ட வரிகள் (பதிவு செய்யப்படவில்லை)",
            photoAckText: "மொத்த வேறுபாடுகள் மற்றும் தவிர்க்கப்பட்ட வரிகளை நான் ஏற்றுக்கொள்கிறேன்.",
            photoTotalMatched: "மொத்தம் சரிபார்க்கப்பட்டது",
            photoTotalMismatch: "மொத்தத்தில் முரண்பாடு உள்ளது",
            uploadingPhoto: "புகைப்படம் செயலாக்கப்படுகிறது...",
            useLatinName: "ஆங்கில பெயர்",
            useTamilName: "தமிழ் பெயர்",
            tryThese: "உதாரணங்கள்:",
            trySampleNotebook: "மாதிரி நோட்புக் பக்கம்",
            howItWorks: "எப்படி செயல்படுகிறது"
        }
    };

    // --- State ---
    let currentLang = localStorage.getItem("kadai_khata_lang") || "en";
    let allCustomers = [];
    let currentDrafts = [];
    let activeCustomer = null;
    let isParsing = false;
    let latestAgentRun = null;

    // --- DOM Elements ---
    const elements = {
        langToggleBtn: document.getElementById("lang-toggle-btn"),
        langCurrentLabel: document.getElementById("lang-current-label"),
        tabLedgerBtn: document.getElementById("tab-ledger-btn"),
        tabCollectionsBtn: document.getElementById("tab-collections-btn"),
        homeView: document.getElementById("home-view"),
        collectionsView: document.getElementById("collections-view"),
        confirmView: document.getElementById("confirm-view"),
        customerDetailView: document.getElementById("customer-detail-view"),
        totalOutstandingAmount: document.getElementById("total-outstanding-amount"),
        customerCountBadge: document.getElementById("customer-count-badge"),
        customerSearchInput: document.getElementById("customer-search-input"),
        searchClearBtn: document.getElementById("search-clear-btn"),
        customerListContainer: document.getElementById("customer-list-container"),
        emptyCustomersState: document.getElementById("empty-customers-state"),
        filteredCount: document.getElementById("filtered-count"),
        // Confirm Cards View
        draftCardsContainer: document.getElementById("draft-cards-container"),
        clarificationBanner: document.getElementById("clarification-banner"),
        clarificationMessage: document.getElementById("clarification-message"),
        confirmAllBtn: document.getElementById("confirm-all-btn"),
        discardAllBtn: document.getElementById("discard-all-btn"),
        // Customer Detail View
        backToHomeBtn: document.getElementById("back-to-home-btn"),
        detailCustomerName: document.getElementById("detail-customer-name"),
        detailCustomerPhone: document.getElementById("detail-customer-phone"),
        detailCustomerBalance: document.getElementById("detail-customer-balance"),
        detailAgingBadge: document.getElementById("detail-aging-badge"),
        timelineContainer: document.getElementById("timeline-container"),
        emptyTimelineState: document.getElementById("empty-timeline-state"),
        openReminderBtn: document.getElementById("open-reminder-btn"),
        // Input Bar
        transcriptionForm: document.getElementById("transcription-form"),
        sentenceInput: document.getElementById("sentence-input"),
        sendBtn: document.getElementById("send-btn"),
        inputStatusBar: document.getElementById("input-status-bar"),
        inputStatusText: document.getElementById("input-status-text"),
        photoCancelBtn: document.getElementById("photo-cancel-btn"),
        // Reminder Modal
        reminderModal: document.getElementById("reminder-modal"),
        closeReminderModalBtn: document.getElementById("close-reminder-modal-btn"),
        reminderCustomerSubtitle: document.getElementById("reminder-customer-subtitle"),
        reminderLangSelect: document.getElementById("reminder-lang-select"),
        reminderToneSelect: document.getElementById("reminder-tone-select"),
        generateReminderBtn: document.getElementById("generate-reminder-btn"),
        generateBtnText: document.getElementById("generate-btn-text"),
        reminderOutputBox: document.getElementById("reminder-output-box"),
        reminderMessageText: document.getElementById("reminder-message-text"),
        reminderVerifiedBadge: document.getElementById("reminder-verified-badge"),
        reminderSourceBadge: document.getElementById("reminder-source-badge"),
        reminderWhatsappLink: document.getElementById("reminder-whatsapp-link"),
        reminderCopyBtn: document.getElementById("reminder-copy-btn"),
        copyBtnLabel: document.getElementById("copy-btn-label"),
        // Collections View Elements
        runCollectionsBtn: document.getElementById("run-collections-btn"),
        runBtnSpinner: document.getElementById("run-btn-spinner"),
        runBtnText: document.getElementById("run-btn-text"),
        collectionsSourceBadge: document.getElementById("collections-source-badge"),
        collectionsChainBadge: document.getElementById("collections-chain-badge"),
        collectionsSummaryBar: document.getElementById("collections-summary-bar"),
        summaryProposedChip: document.getElementById("summary-proposed-chip"),
        summaryVerifiedChip: document.getElementById("summary-verified-chip"),
        summaryRejectedChip: document.getElementById("summary-rejected-chip"),
        planCardsContainer: document.getElementById("plan-cards-container"),
        emptyPlanState: document.getElementById("empty-plan-state"),
        agentTraceWrapper: document.getElementById("agent-trace-wrapper"),
        toggleTraceBtn: document.getElementById("toggle-trace-btn"),
        traceChevron: document.getElementById("trace-chevron"),
        traceStepsCount: document.getElementById("trace-steps-count"),
        agentTraceContent: document.getElementById("agent-trace-content"),
        traceStepsList: document.getElementById("trace-steps-list"),
        // Ask Elements
        askForm: document.getElementById("ask-form"),
        askInput: document.getElementById("ask-input"),
        askSubmitBtn: document.getElementById("ask-submit-btn"),
        askResultBox: document.getElementById("ask-result-box"),
        askVerifiedBadge: document.getElementById("ask-verified-badge"),
        askSourceBadge: document.getElementById("ask-source-badge"),
        askAnswerText: document.getElementById("ask-answer-text"),
        toastContainer: document.getElementById("toast-container"),
        // Photo Upload & Review Elements
        photoFileInput: document.getElementById("photo-file-input"),
        photoUploadBtn: document.getElementById("photo-upload-btn"),
        photoPrivacyBanner: document.getElementById("photo-privacy-banner"),
        photoTotalCheckCard: document.getElementById("photo-total-check-card"),
        photoTotalBadge: document.getElementById("photo-total-badge"),
        totalDraftedUdhaar: document.getElementById("total-drafted-udhaar"),
        totalWrittenUdhaar: document.getElementById("total-written-udhaar"),
        totalDraftedJama: document.getElementById("total-drafted-jama"),
        totalWrittenJama: document.getElementById("total-written-jama"),
        photoTotalMismatchWarning: document.getElementById("photo-total-mismatch-warning"),
        photoAckWrapper: document.getElementById("photo-ack-wrapper"),
        photoAckCheckbox: document.getElementById("photo-ack-checkbox"),
        photoExceptionsCard: document.getElementById("photo-exceptions-card"),
        photoCancelledList: document.getElementById("photo-cancelled-list"),
        photoUnreadableList: document.getElementById("photo-unreadable-list"),
        howItWorksBtn: document.getElementById("how-it-works-btn"),
        howItWorksModal: document.getElementById("how-it-works-modal"),
        closeHowItWorksBtn: document.getElementById("close-how-it-works-btn"),
        trySampleNotebookBtn: document.getElementById("try-sample-notebook-btn")
    };

    let currentPhotoTotalCheck = null;


    // --- Helper: Safe HTML Escaping ---
    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function t(key, vars = {}) {
        let text = (I18N[currentLang] && I18N[currentLang][key]) || (I18N.en && I18N.en[key]) || key;
        for (const [k, v] of Object.entries(vars)) {
            text = text.replace(new RegExp(`\\{${k}\\}`, "g"), v);
        }
        return text;
    }

    function applyTranslations() {
        document.querySelectorAll("[data-i18n]").forEach(el => {
            const key = el.getAttribute("data-i18n");
            el.textContent = t(key);
        });
        document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
            const key = el.getAttribute("data-i18n-placeholder");
            el.setAttribute("placeholder", t(key));
        });
        if (elements.langCurrentLabel) {
            elements.langCurrentLabel.textContent = t("langBtnLabel");
        }
        if (allCustomers.length > 0) {
            elements.customerCountBadge.textContent = t("customersCount", { n: allCustomers.length });
        }
    }

    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        elements.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(-8px)";
            toast.style.transition = "all 0.2s ease";
            setTimeout(() => toast.remove(), 200);
        }, 3200);
    }

    // --- Navigation ---
    function showView(viewName) {
        elements.homeView.style.display = viewName === "home" ? "flex" : "none";
        elements.collectionsView.style.display = viewName === "collections" ? "flex" : "none";
        elements.confirmView.style.display = viewName === "confirm" ? "flex" : "none";
        elements.customerDetailView.style.display = viewName === "detail" ? "flex" : "none";

        if (elements.tabLedgerBtn && elements.tabCollectionsBtn) {
            elements.tabLedgerBtn.classList.toggle("active", viewName === "home");
            elements.tabCollectionsBtn.classList.toggle("active", viewName === "collections");
        }
        window.scrollTo({ top: 0, behavior: "smooth" });
    }


    // --- API Calls ---
    async function loadCustomers() {
        try {
            const resp = await fetch("/api/customers/");
            if (!resp.ok) throw new Error("Failed to load customers");
            const data = await resp.json();
            allCustomers = data.customers || [];
            elements.totalOutstandingAmount.textContent = data.total_outstanding || "0.00";
            elements.customerCountBadge.textContent = t("customersCount", { n: allCustomers.length });
            renderCustomerList();
        } catch (err) {
            showToast(t("errorNetwork"), "error");
        }
    }

    function renderCustomerList() {
        const filter = (elements.customerSearchInput.value || "").trim().toLowerCase();
        elements.customerListContainer.innerHTML = "";

        const filtered = allCustomers.filter(c => {
            if (!filter) return true;
            return c.name.toLowerCase().includes(filter) || (c.phone && c.phone.includes(filter));
        });

        if (filtered.length === 0) {
            elements.emptyCustomersState.style.display = "flex";
            elements.filteredCount.textContent = "";
        } else {
            elements.emptyCustomersState.style.display = "none";
            elements.filteredCount.textContent = filter ? `${filtered.length} / ${allCustomers.length}` : "";
        }

        filtered.forEach(cust => {
            const card = document.createElement("div");
            card.className = "customer-card";
            card.setAttribute("role", "button");
            card.setAttribute("tabindex", "0");
            card.setAttribute("aria-label", `View account for ${cust.name}`);

            const infoDiv = document.createElement("div");
            infoDiv.className = "customer-info";

            const nameEl = document.createElement("div");
            nameEl.className = "customer-name";
            nameEl.textContent = cust.name;

            const metaRow = document.createElement("div");
            metaRow.className = "customer-meta-row";

            if (cust.phone) {
                const phoneSpan = document.createElement("span");
                phoneSpan.textContent = cust.phone;
                metaRow.appendChild(phoneSpan);
            }

            const agingBadge = document.createElement("span");
            const bucket = cust.aging_bucket || "0-30";
            agingBadge.className = `badge badge-aging-${bucket.replace("+", "-plus")}`;
            agingBadge.textContent = bucket;
            metaRow.appendChild(agingBadge);

            const daysSpan = document.createElement("span");
            if (cust.days_since_last_entry === 0 && cust.last_entry_at) {
                daysSpan.textContent = t("today");
            } else if (cust.days_since_last_entry > 0) {
                daysSpan.textContent = t("daysAgo", { n: cust.days_since_last_entry });
            }
            metaRow.appendChild(daysSpan);

            infoDiv.appendChild(nameEl);
            infoDiv.appendChild(metaRow);

            const balanceBlock = document.createElement("div");
            balanceBlock.className = "customer-balance-block";

            const balAmount = document.createElement("div");
            balAmount.className = "customer-balance-amount";
            const balVal = parseFloat(cust.balance || "0");
            if (balVal <= 0) {
                balAmount.classList.add("customer-balance-settled");
            }
            balAmount.textContent = `₹${cust.balance}`;

            balanceBlock.appendChild(balAmount);

            card.appendChild(infoDiv);
            card.appendChild(balanceBlock);

            card.addEventListener("click", () => openCustomerDetail(cust.id));
            card.addEventListener("keydown", (e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    openCustomerDetail(cust.id);
                }
            });

            elements.customerListContainer.appendChild(card);
        });
    }

    // --- Customer Detail & Timeline ---
    async function openCustomerDetail(customerId) {
        try {
            const resp = await fetch(`/api/customers/${customerId}/timeline/`);
            if (!resp.ok) throw new Error("Failed to load customer timeline");
            const data = await resp.json();
            activeCustomer = data.customer;
            renderCustomerDetail(data);
            showView("detail");
        } catch (err) {
            showToast(t("errorNetwork"), "error");
        }
    }

    function renderCustomerDetail(data) {
        const cust = data.customer;
        elements.detailCustomerName.textContent = cust.name;
        elements.detailCustomerPhone.textContent = cust.phone ? `Phone: ${cust.phone}` : "";
        elements.detailCustomerBalance.textContent = cust.balance;

        const bucket = cust.aging_bucket || "0-30";
        elements.detailAgingBadge.className = `badge badge-aging-${bucket.replace("+", "-plus")}`;
        elements.detailAgingBadge.textContent = bucket;

        elements.timelineContainer.innerHTML = "";
        const entries = data.entries || [];

        if (entries.length === 0) {
            elements.emptyTimelineState.style.display = "flex";
        } else {
            elements.emptyTimelineState.style.display = "none";
        }

        entries.forEach(entry => {
            const card = document.createElement("div");
            card.className = "timeline-entry-card";
            if (entry.has_been_reversed) {
                card.classList.add("entry-reversed");
            }

            // Top row: kind & amount
            const topRow = document.createElement("div");
            topRow.className = "timeline-entry-top";

            const kindPill = document.createElement("div");
            kindPill.className = "timeline-kind-pill";

            const isCredit = entry.kind === "credit_given";
            kindPill.style.color = isCredit ? "var(--credit-red)" : "var(--payment-green)";
            kindPill.textContent = isCredit ? `▲ ${t("udhaar")}` : `▼ ${t("varavu")}`;

            const amountEl = document.createElement("div");
            amountEl.className = "timeline-amount";
            amountEl.style.color = isCredit ? "var(--credit-red)" : "var(--payment-green)";
            amountEl.textContent = `${isCredit ? "+" : "-"}₹${entry.amount}`;

            topRow.appendChild(kindPill);
            topRow.appendChild(amountEl);

            // Meta row: date and running balance
            const metaRow = document.createElement("div");
            metaRow.className = "timeline-meta-row";

            const dateSpan = document.createElement("span");
            const dt = new Date(entry.created_at);
            dateSpan.textContent = dt.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

            const balSpan = document.createElement("span");
            balSpan.className = "timeline-running-bal";
            balSpan.textContent = `Bal: ₹${entry.running_balance}`;

            metaRow.appendChild(dateSpan);
            metaRow.appendChild(balSpan);

            card.appendChild(topRow);
            card.appendChild(metaRow);

            // Note or original source
            if (entry.note) {
                const noteEl = document.createElement("div");
                noteEl.className = "timeline-note";
                noteEl.textContent = entry.note;
                card.appendChild(noteEl);
            }

            // Audit Badges
            if (entry.is_reversal) {
                const revBadge = document.createElement("span");
                revBadge.className = "badge badge-mock";
                revBadge.textContent = t("reversalEntryBadge");
                card.appendChild(revBadge);
            }
            if (entry.has_been_reversed) {
                const revBadge = document.createElement("span");
                revBadge.className = "badge badge-warning";
                revBadge.textContent = `${t("reversedBadge")} (#${entry.reversal_id})`;
                card.appendChild(revBadge);
            }

            // Reverse Button (Audit Trail: no deletes)
            if (!entry.has_been_reversed && !entry.is_reversal) {
                const actionsRow = document.createElement("div");
                actionsRow.className = "timeline-actions";

                const revBtn = document.createElement("button");
                revBtn.type = "button";
                revBtn.className = "btn btn-danger btn-sm";
                revBtn.textContent = `↩ ${t("reverseEntry")}`;
                revBtn.addEventListener("click", () => handleReverseEntry(entry.id));

                actionsRow.appendChild(revBtn);
                card.appendChild(actionsRow);
            }

            elements.timelineContainer.appendChild(card);
        });
    }

    async function handleReverseEntry(entryId) {
        const reason = window.prompt(t("reversalPrompt"), "");
        if (reason === null) return; // user cancelled

        try {
            const resp = await fetch("/api/reverse/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ entry_id: entryId, reason: reason })
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || "Reversal failed");

            showToast(t("reversalSuccess"), "success");
            // Refresh detail view & background customers
            if (activeCustomer) {
                await openCustomerDetail(activeCustomer.id);
            }
            loadCustomers();
        } catch (err) {
            showToast(err.message, "error");
        }
    }

    // --- Sentence Parsing & Draft Cards ---
    async function handleSentenceSubmit() {
        const text = elements.sentenceInput.value.trim();
        if (!text || isParsing) return;

        isParsing = true;
        elements.inputStatusBar.style.display = "flex";
        elements.sendBtn.disabled = true;

        try {
            const resp = await fetch("/api/parse/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: text })
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || "Parsing failed");

            elements.sentenceInput.value = "";
            currentDrafts = data.drafts || [];

            // Clarification question from model
            if (data.clarification) {
                elements.clarificationMessage.textContent = data.clarification;
                elements.clarificationBanner.style.display = "flex";
            } else {
                elements.clarificationBanner.style.display = "none";
            }

            clearPhotoReviewUI();
            renderDraftCards(currentDrafts);
            showView("confirm");
        } catch (err) {
            showToast(err.message, "error");
        } finally {
            isParsing = false;
            elements.inputStatusBar.style.display = "none";
            elements.sendBtn.disabled = false;
        }
    }

    // --- Photo Digitizer (Client-side downscale & EXIF strip) ---
    function downscaleImageToBlob(file, maxEdge = 1600) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(new Error("Failed to read image file."));
            reader.onload = (e) => {
                const img = new Image();
                img.onerror = () => reject(new Error("Failed to decode image."));
                img.onload = () => {
                    let w = img.width;
                    let h = img.height;
                    if (Math.max(w, h) > maxEdge) {
                        const scale = maxEdge / Math.max(w, h);
                        w = Math.round(w * scale);
                        h = Math.round(h * scale);
                    }
                    const canvas = document.createElement("canvas");
                    canvas.width = w;
                    canvas.height = h;
                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0, w, h);
                    canvas.toBlob(
                        (blob) => {
                            if (blob) resolve(blob);
                            else reject(new Error("Canvas blob conversion failed."));
                        },
                        "image/jpeg",
                        0.85
                    );
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        });
    }

    async function handlePhotoFileSelected(file) {
        if (!file || isParsing) return;

        isParsing = true;
        elements.inputStatusBar.style.display = "flex";
        if (elements.photoCancelBtn) {
            elements.photoCancelBtn.style.display = "inline-block";
        }
        elements.sendBtn.disabled = true;

        let elapsedSeconds = 0;
        elements.inputStatusText.textContent = `Reading the page... can take up to 30 seconds (${elapsedSeconds}s)`;
        const photoTimer = setInterval(() => {
            elapsedSeconds++;
            elements.inputStatusText.textContent = `Reading the page... can take up to 30 seconds (${elapsedSeconds}s)`;
        }, 1000);

        const abortController = new AbortController();
        const onCancelClick = () => {
            abortController.abort();
        };
        if (elements.photoCancelBtn) {
            elements.photoCancelBtn.addEventListener("click", onCancelClick, { once: true });
        }

        try {
            const scaledBlob = await downscaleImageToBlob(file, 1600);
            const formData = new FormData();
            formData.append("image", scaledBlob, "notebook_page.jpg");

            const resp = await fetch("/api/parse-photo/", {
                method: "POST",
                body: formData,
                signal: abortController.signal,
            });
            const data = await resp.json();
            if (!resp.ok || data.status === "error") {
                throw new Error(data.error || "Photo parsing failed");
            }

            currentDrafts = data.drafts || [];
            currentPhotoTotalCheck = data.total_check || null;

            renderPhotoReviewUI(data);
            renderDraftCards(currentDrafts);
            showView("confirm");
        } catch (err) {
            if (err.name === "AbortError") {
                showToast("Photo reading was cancelled.", "info");
            } else {
                showToast(err.message, "error");
            }
        } finally {
            clearInterval(photoTimer);
            isParsing = false;
            elements.inputStatusBar.style.display = "none";
            if (elements.photoCancelBtn) {
                elements.photoCancelBtn.style.display = "none";
                elements.photoCancelBtn.removeEventListener("click", onCancelClick);
            }
            elements.sendBtn.disabled = false;
            if (elements.photoFileInput) elements.photoFileInput.value = "";
        }
    }

    function renderPhotoReviewUI(data) {
        if (elements.photoPrivacyBanner) elements.photoPrivacyBanner.style.display = "flex";

        if (data.total_check && elements.photoTotalCheckCard) {
            elements.photoTotalCheckCard.style.display = "block";
            const tc = data.total_check;
            if (elements.totalDraftedUdhaar) elements.totalDraftedUdhaar.textContent = Number(tc.sum_udhaar || 0).toFixed(2);
            if (elements.totalWrittenUdhaar) elements.totalWrittenUdhaar.textContent = tc.total_udhaar !== null && tc.total_udhaar !== undefined ? `₹${Number(tc.total_udhaar).toFixed(2)}` : "-";

            if (elements.totalDraftedJama) elements.totalDraftedJama.textContent = Number(tc.sum_jama || 0).toFixed(2);
            if (elements.totalWrittenJama) elements.totalWrittenJama.textContent = tc.total_jama !== null && tc.total_jama !== undefined ? `₹${Number(tc.total_jama).toFixed(2)}` : "-";

            if (tc.has_mismatch) {
                if (elements.photoTotalBadge) {
                    elements.photoTotalBadge.className = "badge badge-warning";
                    elements.photoTotalBadge.textContent = t("photoTotalMismatch");
                }
                if (elements.photoTotalMismatchWarning) {
                    elements.photoTotalMismatchWarning.textContent = tc.warning || "Column totals mismatch.";
                    elements.photoTotalMismatchWarning.style.display = "block";
                }
                if (elements.photoAckWrapper) elements.photoAckWrapper.style.display = "block";
                if (elements.photoAckCheckbox) elements.photoAckCheckbox.checked = false;
            } else {
                if (elements.photoTotalBadge) {
                    elements.photoTotalBadge.className = "badge badge-success";
                    elements.photoTotalBadge.textContent = t("photoTotalMatched");
                }
                if (elements.photoTotalMismatchWarning) elements.photoTotalMismatchWarning.style.display = "none";
                if (elements.photoAckWrapper) elements.photoAckWrapper.style.display = "none";
                if (elements.photoAckCheckbox) elements.photoAckCheckbox.checked = true;
            }
        } else if (elements.photoTotalCheckCard) {
            elements.photoTotalCheckCard.style.display = "none";
        }

        const cancelled = data.cancelled_rows || [];
        const unreadable = data.unreadable_rows || [];
        if ((cancelled.length > 0 || unreadable.length > 0) && elements.photoExceptionsCard) {
            elements.photoExceptionsCard.style.display = "block";
            if (elements.photoCancelledList) elements.photoCancelledList.innerHTML = "";
            if (elements.photoUnreadableList) elements.photoUnreadableList.innerHTML = "";

            cancelled.forEach(c => {
                const chip = document.createElement("span");
                chip.className = "exception-chip";
                chip.textContent = `❌ ${c.row_hint || "Cancelled row"}`;
                if (elements.photoCancelledList) elements.photoCancelledList.appendChild(chip);
            });

            unreadable.forEach(u => {
                const chip = document.createElement("span");
                chip.className = "exception-chip";
                chip.textContent = `⚠ ${u.row_hint || "Unreadable"}: ${u.reason || "illegible"}`;
                if (elements.photoUnreadableList) elements.photoUnreadableList.appendChild(chip);
            });
        } else if (elements.photoExceptionsCard) {
            elements.photoExceptionsCard.style.display = "none";
        }
    }

    function clearPhotoReviewUI() {
        if (elements.photoPrivacyBanner) elements.photoPrivacyBanner.style.display = "none";
        if (elements.photoTotalCheckCard) elements.photoTotalCheckCard.style.display = "none";
        if (elements.photoExceptionsCard) elements.photoExceptionsCard.style.display = "none";
        if (elements.photoCancelledList) elements.photoCancelledList.innerHTML = "";
        if (elements.photoUnreadableList) elements.photoUnreadableList.innerHTML = "";
        currentPhotoTotalCheck = null;
    }

    function updateConfirmAllState() {
        if (!elements.confirmAllBtn) return;
        const hasNonExact = currentDrafts.some(d => !d.is_exact_match);
        const hasUnackedMismatch = Boolean(
            currentPhotoTotalCheck &&
            currentPhotoTotalCheck.has_mismatch &&
            elements.photoAckCheckbox &&
            !elements.photoAckCheckbox.checked
        );

        const shouldDisable = hasNonExact || hasUnackedMismatch;
        elements.confirmAllBtn.disabled = shouldDisable;

        if (hasUnackedMismatch) {
            elements.confirmAllBtn.title = "Acknowledge column totals mismatch and skipped rows to enable Confirm All";
            elements.confirmAllBtn.style.opacity = "0.5";
            elements.confirmAllBtn.style.cursor = "not-allowed";
        } else if (hasNonExact) {
            elements.confirmAllBtn.title = "Confirm all is disabled: resolve suggested or non-exact matches first";
            elements.confirmAllBtn.style.opacity = "0.5";
            elements.confirmAllBtn.style.cursor = "not-allowed";
        } else {
            elements.confirmAllBtn.title = "";
            elements.confirmAllBtn.style.opacity = "1";
            elements.confirmAllBtn.style.cursor = "pointer";
        }
    }

    function renderDraftCards(drafts) {
        elements.draftCardsContainer.innerHTML = "";
        elements.confirmAllBtn.style.display = drafts.length > 1 ? "inline-flex" : "none";

        // Disable "Confirm all" while any draft has a non-exact match or unacknowledged photo mismatch
        updateConfirmAllState();

        if (drafts.length === 0) {
            if (!elements.clarificationMessage.textContent) {
                showView("home");
            }
            return;
        }

        drafts.forEach(draft => {
            const card = document.createElement("div");
            card.className = "draft-card";
            card.id = `draft-card-${draft.id}`;

            // Badges row
            const badgesRow = document.createElement("div");
            badgesRow.className = "draft-badges-row";

            // Source Badge with honest colors
            const sourceBadge = document.createElement("span");
            const src = (draft.source_label || "mock").toLowerCase();
            sourceBadge.className = `badge badge-${src}`;
            sourceBadge.textContent = src.toUpperCase();
            badgesRow.appendChild(sourceBadge);

            // Match badge (exact match vs suggestion vs new)
            const matchBadge = document.createElement("span");
            if (draft.is_exact_match) {
                matchBadge.className = "badge badge-match";
                matchBadge.textContent = t("matchesCustomer");
            } else if (draft.candidates && draft.candidates.length > 0) {
                matchBadge.className = "badge badge-fallback";
                matchBadge.textContent = `Suggestion: ${draft.candidates[0]}`;
            } else {
                matchBadge.className = "badge badge-new";
                matchBadge.textContent = t("newCustomer");
            }
            badgesRow.appendChild(matchBadge);

            // Warnings
            if (draft.warnings && draft.warnings.length > 0) {
                draft.warnings.forEach(warn => {
                    const wBadge = document.createElement("span");
                    wBadge.className = "badge badge-warning";
                    wBadge.textContent = `⚠ ${warn}`;
                    badgesRow.appendChild(wBadge);
                });
            }

            card.appendChild(badgesRow);

            // Candidate Chooser / Change Option for non-exact matches or ambiguous candidates
            let selectedCandidateName = draft.customer_name;
            if (draft.candidates && draft.candidates.length > 0 && !draft.is_exact_match) {
                const pickerBox = document.createElement("div");
                pickerBox.className = "candidate-picker-box";

                const pTitle = document.createElement("div");
                pTitle.className = "candidate-picker-title";
                pTitle.textContent = "Suggested Customer (Click to apply match):";
                pickerBox.appendChild(pTitle);

                const optsRow = document.createElement("div");
                optsRow.className = "candidate-options-row";

                draft.candidates.forEach(cand => {
                    const chip = document.createElement("button");
                    chip.type = "button";
                    chip.className = "candidate-chip-btn";
                    if (cand === selectedCandidateName) chip.classList.add("selected");
                    chip.textContent = cand;

                    chip.addEventListener("click", () => {
                        selectedCandidateName = cand;
                        custInput.value = cand;
                        draft.customer_name = cand;
                        draft.is_exact_match = true;
                        matchBadge.className = "badge badge-match";
                        matchBadge.textContent = `${t("matchesCustomer")} (${cand})`;
                        pickerBox.querySelectorAll(".candidate-chip-btn").forEach(c => c.classList.remove("selected"));
                        chip.classList.add("selected");

                        // Recheck if all drafts now have exact matches
                        const stillNonExact = drafts.some(d => !d.is_exact_match);
                        elements.confirmAllBtn.disabled = stillNonExact;
                        if (!stillNonExact) {
                            elements.confirmAllBtn.title = "";
                            elements.confirmAllBtn.style.opacity = "1";
                            elements.confirmAllBtn.style.cursor = "pointer";
                        }
                    });

                    optsRow.appendChild(chip);
                });

                pickerBox.appendChild(optsRow);
                card.appendChild(pickerBox);
            }

            // Customer Name Input
            const custGroup = document.createElement("div");
            custGroup.className = "draft-form-group";
            const custLabel = document.createElement("label");
            custLabel.className = "draft-label";
            custLabel.textContent = "Customer Name";
            const custInput = document.createElement("input");
            custInput.type = "text";
            custInput.className = "draft-input";
            custGroup.appendChild(custLabel);
            custGroup.appendChild(custInput);

            // Tamil Name & Latin suggestion toggle
            if (draft.name_latin && draft.name_latin !== draft.customer_name) {
                const originalName = draft.customer_name;
                const latinSuggestion = draft.name_latin;
                const toggleChip = document.createElement("button");
                toggleChip.type = "button";
                toggleChip.className = "latin-toggle-chip";
                let isUsingLatin = false;
                toggleChip.textContent = `🔤 ${t("useLatinName")}: ${latinSuggestion}`;
                toggleChip.addEventListener("click", () => {
                    isUsingLatin = !isUsingLatin;
                    if (isUsingLatin) {
                        custInput.value = latinSuggestion;
                        draft.customer_name = latinSuggestion;
                        toggleChip.textContent = `🔤 ${t("useTamilName")}: ${originalName}`;
                    } else {
                        custInput.value = originalName;
                        draft.customer_name = originalName;
                        toggleChip.textContent = `🔤 ${t("useLatinName")}: ${latinSuggestion}`;
                    }
                    updateConfirmAllState();
                });
                custGroup.appendChild(toggleChip);
            }

            card.appendChild(custGroup);

            // Kind Toggle (Udhaar / Varavu)
            const kindGroup = document.createElement("div");
            kindGroup.className = "draft-form-group";
            const kindLabel = document.createElement("label");
            kindLabel.className = "draft-label";
            kindLabel.textContent = "Transaction Kind";

            const toggleGroup = document.createElement("div");
            toggleGroup.className = "kind-toggle-group";

            let currentKind = draft.kind;

            const creditBtn = document.createElement("button");
            creditBtn.type = "button";
            creditBtn.className = "kind-toggle-btn kind-credit" + (currentKind === "credit_given" ? " active" : "");
            creditBtn.textContent = `▲ ${t("udhaar")}`;

            const paymentBtn = document.createElement("button");
            paymentBtn.type = "button";
            paymentBtn.className = "kind-toggle-btn kind-payment" + (currentKind === "payment_received" ? " active" : "");
            paymentBtn.textContent = `▼ ${t("varavu")}`;

            creditBtn.addEventListener("click", () => {
                currentKind = "credit_given";
                creditBtn.classList.add("active");
                paymentBtn.classList.remove("active");
            });

            paymentBtn.addEventListener("click", () => {
                currentKind = "payment_received";
                paymentBtn.classList.add("active");
                creditBtn.classList.remove("active");
            });

            toggleGroup.appendChild(creditBtn);
            toggleGroup.appendChild(paymentBtn);
            kindGroup.appendChild(kindLabel);
            kindGroup.appendChild(toggleGroup);
            card.appendChild(kindGroup);

            // Amount Input
            const amtGroup = document.createElement("div");
            amtGroup.className = "draft-form-group";
            const amtLabel = document.createElement("label");
            amtLabel.className = "draft-label";
            amtLabel.textContent = "Amount (₹)";
            const amtInput = document.createElement("input");
            amtInput.type = "number";
            amtInput.step = "0.01";
            amtInput.className = "draft-input";
            amtInput.value = draft.amount;
            amtGroup.appendChild(amtLabel);
            amtGroup.appendChild(amtInput);
            card.appendChild(amtGroup);

            // Note Input
            const noteGroup = document.createElement("div");
            noteGroup.className = "draft-form-group";
            const noteLabel = document.createElement("label");
            noteLabel.className = "draft-label";
            noteLabel.textContent = "Note / Items";
            const noteInput = document.createElement("input");
            noteInput.type = "text";
            noteInput.className = "draft-input";
            noteInput.value = draft.note || "";
            noteGroup.appendChild(noteLabel);
            noteGroup.appendChild(noteInput);
            card.appendChild(noteGroup);

            // Action Buttons: Confirm and Reject
            const actionsRow = document.createElement("div");
            actionsRow.className = "draft-actions-row";

            const rejectBtn = document.createElement("button");
            rejectBtn.type = "button";
            rejectBtn.className = "btn btn-secondary";
            rejectBtn.textContent = t("reject");
            rejectBtn.addEventListener("click", () => handleRejectDraft(draft.id));

            const confirmBtn = document.createElement("button");
            confirmBtn.type = "button";
            confirmBtn.className = "btn btn-primary";
            confirmBtn.textContent = `✔ ${t("confirm")}`;
            confirmBtn.addEventListener("click", () => {
                const edits = {
                    customer_name: custInput.value.trim(),
                    kind: currentKind,
                    amount: amtInput.value.trim(),
                    note: noteInput.value.trim()
                };
                handleConfirmDraft(draft.id, edits);
            });

            actionsRow.appendChild(rejectBtn);
            actionsRow.appendChild(confirmBtn);
            card.appendChild(actionsRow);

            elements.draftCardsContainer.appendChild(card);
        });
    }

    async function handleConfirmDraft(draftId, edits) {
        try {
            const resp = await fetch("/api/confirm/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ draft_id: draftId, edits: edits })
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || "Confirmation failed");

            showToast(t("confirmSuccess"), "success");
            currentDrafts = currentDrafts.filter(d => d.id !== draftId);
            renderDraftCards(currentDrafts);
            loadCustomers();
        } catch (err) {
            showToast(err.message, "error");
        }
    }

    async function handleRejectDraft(draftId) {
        try {
            const resp = await fetch("/api/reject/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ draft_id: draftId })
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || "Reject failed");

            showToast(t("rejectSuccess"), "info");
            currentDrafts = currentDrafts.filter(d => d.id !== draftId);
            renderDraftCards(currentDrafts);
        } catch (err) {
            showToast(err.message, "error");
        }
    }

    async function handleConfirmAll() {
        if (currentDrafts.length === 0) return;
        const draftsToConfirm = [...currentDrafts];
        for (const draft of draftsToConfirm) {
            const cardEl = document.getElementById(`draft-card-${draft.id}`);
            let edits = null;
            if (cardEl) {
                const inputs = cardEl.querySelectorAll("input");
                const activeKindBtn = cardEl.querySelector(".kind-toggle-btn.active");
                const kind = activeKindBtn && activeKindBtn.classList.contains("kind-payment") ? "payment_received" : "credit_given";
                edits = {
                    customer_name: inputs[0] ? inputs[0].value.trim() : draft.customer_name,
                    kind: kind,
                    amount: inputs[1] ? inputs[1].value.trim() : draft.amount,
                    note: inputs[2] ? inputs[2].value.trim() : draft.note
                };
            }
            await handleConfirmDraft(draft.id, edits);
        }
    }

    // --- Verifiable Payment Reminder Modal ---
    function openReminderModal() {
        if (!activeCustomer) return;
        elements.reminderCustomerSubtitle.textContent = `${activeCustomer.name} (Balance: ₹${activeCustomer.balance})`;
        elements.reminderOutputBox.style.display = "none";
        elements.reminderModal.style.display = "flex";
    }

    function closeReminderModal() {
        elements.reminderModal.style.display = "none";
    }

    async function handleGenerateReminder() {
        if (!activeCustomer) return;

        const lang = elements.reminderLangSelect.value;
        const tone = elements.reminderToneSelect.value;

        elements.generateReminderBtn.disabled = true;
        elements.generateBtnText.textContent = "Generating...";

        try {
            const resp = await fetch("/api/reminder/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    customer_id: activeCustomer.id,
                    language: lang,
                    tone: tone
                })
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || "Failed to generate reminder");

            // Display Output
            elements.reminderMessageText.textContent = data.message;

            // Verified Badge
            if (data.verified) {
                elements.reminderVerifiedBadge.style.display = "inline-flex";
            } else {
                elements.reminderVerifiedBadge.style.display = "none";
            }

            // Source Label
            const src = (data.source_label || "mock").toLowerCase();
            elements.reminderSourceBadge.className = `badge badge-${src}`;
            elements.reminderSourceBadge.textContent = src.toUpperCase();

            // WhatsApp link (wa.me) or copy button
            if (data.whatsapp_url) {
                elements.reminderWhatsappLink.href = data.whatsapp_url;
                elements.reminderWhatsappLink.style.display = "inline-flex";
            } else {
                elements.reminderWhatsappLink.style.display = "none";
            }

            elements.reminderOutputBox.style.display = "flex";
        } catch (err) {
            showToast(err.message, "error");
        } finally {
            elements.generateReminderBtn.disabled = false;
            elements.generateBtnText.textContent = t("generateDraft");
        }
    }

    function handleCopyMessage() {
        const text = elements.reminderMessageText.textContent;
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            elements.copyBtnLabel.textContent = t("copied");
            setTimeout(() => {
                elements.copyBtnLabel.textContent = t("copyMessage");
            }, 2000);
        }).catch(() => {
            showToast("Failed to copy to clipboard", "error");
        });
    }

    // --- Ask Balance Feature ---
    async function handleAskSubmit(e) {
        if (e) e.preventDefault();
        const q = (elements.askInput.value || "").trim();
        if (!q) return;

        elements.askSubmitBtn.disabled = true;
        elements.askSubmitBtn.textContent = "...";
        try {
            const resp = await fetch("/api/ask/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: q }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || "Failed to get answer");

            elements.askAnswerText.textContent = data.answer;
            const src = (data.source_label || "mock").toLowerCase();
            elements.askSourceBadge.className = `badge badge-${src}`;
            elements.askSourceBadge.textContent = src.toUpperCase();
            elements.askVerifiedBadge.style.display = data.verified ? "inline-block" : "none";
            elements.askResultBox.style.display = "block";
        } catch (err) {
            showToast(err.message, "error");
        } finally {
            elements.askSubmitBtn.disabled = false;
            elements.askSubmitBtn.textContent = t("askBtn");
        }
    }

    // --- Daily Collections Agent Feature ---
    async function handleRunCollectionsReview() {
        elements.runCollectionsBtn.disabled = true;
        elements.runBtnSpinner.style.display = "inline-block";
        elements.runBtnText.textContent = t("runningReview");

        try {
            const resp = await fetch("/api/agent/run/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({}),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || "Collections review failed");

            latestAgentRun = data.run;
            renderCollectionsPlan(data.run);
            showToast(t("runReviewSuccess"), "success");
        } catch (err) {
            showToast(err.message, "error");
        } finally {
            elements.runCollectionsBtn.disabled = false;
            elements.runBtnSpinner.style.display = "none";
            elements.runBtnText.textContent = t("runCollectionsReview");
        }
    }

    function renderCollectionsPlan(run) {
        if (!run || !run.plan) return;

        const plan = run.plan;
        const actions = plan.actions || [];
        const summary = plan.summary || { proposed_count: actions.length, verified_count: actions.length, rejected_count: 0 };

        // Badges
        const src = (run.source_label || "mock").toLowerCase();
        elements.collectionsSourceBadge.className = `badge badge-${src}`;
        elements.collectionsSourceBadge.textContent = src.toUpperCase();
        elements.collectionsSourceBadge.style.display = "inline-block";

        elements.collectionsChainBadge.style.display = "inline-block";
        if (run.chain_valid) {
            elements.collectionsChainBadge.className = "badge badge-success";
            elements.collectionsChainBadge.textContent = `🔗 ${t("chainValid")}`;
        } else {
            elements.collectionsChainBadge.className = "badge badge-warning";
            elements.collectionsChainBadge.textContent = `⚠️ ${t("chainInvalid")}`;
        }

        // Summary Bar
        elements.summaryProposedChip.textContent = `Proposed: ${summary.proposed_count}`;
        elements.summaryVerifiedChip.textContent = `✓ Verified: ${summary.verified_count}`;
        elements.summaryRejectedChip.textContent = `⚠ Unverified: ${summary.rejected_count}`;
        elements.collectionsSummaryBar.style.display = "flex";

        // Plan Cards
        elements.planCardsContainer.innerHTML = "";
        if (actions.length === 0) {
            elements.emptyPlanState.style.display = "flex";
        } else {
            elements.emptyPlanState.style.display = "none";
        }

        actions.forEach((a, idx) => {
            const card = document.createElement("div");
            card.className = `plan-card ${a.verified ? "" : "unverified-card"}`;
            card.id = `plan-card-${idx}`;

            // Header Row: Customer Name & Action/Verified Badges
            const headerRow = document.createElement("div");
            headerRow.className = "plan-card-header";

            const nameEl = document.createElement("span");
            nameEl.className = "plan-cust-name";
            nameEl.textContent = a.customer_name || `Customer #${a.customer_id}`;
            nameEl.title = "View customer details";
            nameEl.addEventListener("click", () => {
                openCustomerDetail(a.customer_id);
            });
            headerRow.appendChild(nameEl);

            const badgesCol = document.createElement("div");
            badgesCol.style.display = "flex";
            badgesCol.style.gap = "4px";
            badgesCol.style.flexWrap = "wrap";
            badgesCol.style.justifyContent = "flex-end";

            // Action Badge
            const actBadge = document.createElement("span");
            if (a.action === "remind_now") {
                actBadge.className = "badge badge-match";
                actBadge.textContent = t("actionRemindNow");
            } else if (a.action === "call_personally") {
                actBadge.className = "badge badge-warning";
                actBadge.textContent = t("actionCallPersonally");
            } else {
                actBadge.className = "badge badge-neutral";
                actBadge.textContent = t("actionWait");
            }
            badgesCol.appendChild(actBadge);

            // Tone Badge
            const toneBadge = document.createElement("span");
            toneBadge.className = "badge badge-neutral";
            toneBadge.textContent = a.tone === "firm" ? t("toneFirmBadge") : t("toneSoftBadge");
            badgesCol.appendChild(toneBadge);

            // Verified Badge
            const vBadge = document.createElement("span");
            if (a.verified) {
                vBadge.className = "badge badge-success";
                vBadge.textContent = `✓ ${t("verifiedBadge")}`;
            } else {
                vBadge.className = "badge badge-warning";
                vBadge.textContent = `⚠ ${t("unverifiedBadge")}`;
            }
            badgesCol.appendChild(vBadge);

            headerRow.appendChild(badgesCol);
            card.appendChild(headerRow);

            // Stats Row: Balance & Days Overdue
            const statsRow = document.createElement("div");
            statsRow.className = "plan-stats-row";

            let balText = `₹${parseFloat(a.claimed_balance || 0).toFixed(2)}`;
            if (!a.verified && a.true_balance !== undefined) {
                balText += ` (True: ₹${parseFloat(a.true_balance).toFixed(2)})`;
            }
            const balEl = document.createElement("span");
            balEl.className = "plan-bal-val";
            balEl.textContent = balText;
            statsRow.appendChild(balEl);

            let daysText = `${a.claimed_days_overdue}d overdue`;
            if (!a.verified && a.true_days_overdue !== undefined) {
                daysText += ` (True: ${a.true_days_overdue}d)`;
            }
            const daysEl = document.createElement("span");
            daysEl.className = "plan-days-val";
            daysEl.textContent = daysText;
            statsRow.appendChild(daysEl);

            card.appendChild(statsRow);

            // Reason Box
            const reasonBox = document.createElement("div");
            reasonBox.className = "plan-reason-box";
            reasonBox.textContent = a.reason;
            card.appendChild(reasonBox);

            // Evidence Chips Row
            const evidenceIds = a.evidence_entry_ids || [];
            if (evidenceIds.length > 0) {
                const evRow = document.createElement("div");
                evRow.className = "plan-evidence-row";

                const evLabel = document.createElement("span");
                evLabel.textContent = `${t("evidenceTitle")} `;
                evRow.appendChild(evLabel);

                evidenceIds.forEach(eid => {
                    const chip = document.createElement("button");
                    chip.type = "button";
                    chip.className = "evidence-chip";
                    chip.textContent = `#${eid}`;
                    chip.title = `View entry #${eid} in customer timeline`;
                    chip.addEventListener("click", () => {
                        openEvidenceEntry(a.customer_id, eid);
                    });
                    evRow.appendChild(chip);
                });

                card.appendChild(evRow);
            }

            // Failed checks (if unverified)
            if (!a.verified && a.failed_checks && a.failed_checks.length > 0) {
                const failBox = document.createElement("div");
                failBox.className = "failed-checks-box";
                failBox.textContent = `${t("failedChecksTitle")} ${a.failed_checks.join(", ")}`;
                card.appendChild(failBox);
            }

            // Action Buttons Row (Draft Reminder & Skip)
            const actionsRow = document.createElement("div");
            actionsRow.className = "plan-actions-row";

            const draftBtn = document.createElement("button");
            draftBtn.type = "button";
            draftBtn.className = "btn btn-primary btn-sm";
            draftBtn.textContent = `📢 ${t("draftReminderBtn")}`;
            draftBtn.addEventListener("click", () => {
                handleApproveReminder(run.id, a.customer_id);
            });
            actionsRow.appendChild(draftBtn);

            const skipBtn = document.createElement("button");
            skipBtn.type = "button";
            skipBtn.className = "btn btn-secondary btn-sm";
            skipBtn.textContent = t("skipBtn");
            skipBtn.addEventListener("click", () => {
                card.style.opacity = "0.35";
                card.style.transform = "scale(0.98)";
                card.style.pointerEvents = "none";
            });
            actionsRow.appendChild(skipBtn);

            card.appendChild(actionsRow);
            elements.planCardsContainer.appendChild(card);
        });

        // Setup Agent Trace details
        loadAndRenderTrace(run.id);
    }

    async function loadAndRenderTrace(runId) {
        try {
            const resp = await fetch(`/api/agent/run/${runId}/`);
            if (!resp.ok) return;
            const data = await resp.json();
            const run = data.run;
            const steps = run.steps || [];

            elements.traceStepsCount.textContent = `${steps.length} steps`;
            elements.agentTraceWrapper.style.display = "block";
            elements.traceStepsList.innerHTML = "";

            steps.forEach(s => {
                const item = document.createElement("div");
                item.className = "trace-step-item";

                const hdr = document.createElement("div");
                hdr.className = "trace-step-header";

                const nameTag = document.createElement("span");
                nameTag.className = "trace-step-name";
                nameTag.textContent = `#${s.index} [${s.kind}] ${s.name}`;
                hdr.appendChild(nameTag);

                const hashTag = document.createElement("span");
                hashTag.className = "trace-step-hash";
                hashTag.textContent = s.step_hash ? s.step_hash.substring(0, 10) + "..." : "";
                hashTag.title = `Hash: ${s.step_hash}\nPrev: ${s.prev_hash}`;
                hdr.appendChild(hashTag);

                item.appendChild(hdr);

                const sumEl = document.createElement("div");
                sumEl.className = "trace-step-summary";
                sumEl.textContent = `${s.summary} (${s.latency_ms}ms, ${s.tokens} tok)`;
                item.appendChild(sumEl);

                elements.traceStepsList.appendChild(item);
            });
        } catch (e) {
            console.error("Failed to load agent trace", e);
        }
    }

    function toggleTrace() {
        const isHidden = elements.agentTraceContent.style.display === "none";
        elements.agentTraceContent.style.display = isHidden ? "block" : "none";
        elements.traceChevron.classList.toggle("open", isHidden);
    }

    async function openEvidenceEntry(customerId, entryId) {
        await openCustomerDetail(customerId);
        setTimeout(() => {
            const entryEl = document.getElementById(`timeline-entry-${entryId}`);
            if (entryEl) {
                entryEl.scrollIntoView({ behavior: "smooth", block: "center" });
                entryEl.style.outline = "2px solid var(--primary)";
                setTimeout(() => {
                    entryEl.style.outline = "none";
                    entryEl.style.transition = "outline 0.5s ease";
                }, 2500);
            }
        }, 300);
    }

    async function handleApproveReminder(runId, customerId) {
        try {
            const resp = await fetch("/api/agent/approve/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ run_id: runId, customer_id: customerId }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || "Approval draft failed");

            // Open reminder modal with the generated draft
            elements.reminderCustomerSubtitle.textContent = `${data.customer_name} (₹${data.balance})`;
            elements.reminderMessageText.textContent = data.message;
            elements.reminderVerifiedBadge.style.display = data.verified ? "inline-flex" : "none";

            const src = (data.source_label || "mock").toLowerCase();
            elements.reminderSourceBadge.className = `badge badge-${src}`;
            elements.reminderSourceBadge.textContent = src.toUpperCase();

            if (data.whatsapp_url) {
                elements.reminderWhatsappLink.href = data.whatsapp_url;
                elements.reminderWhatsappLink.style.display = "inline-flex";
            } else {
                elements.reminderWhatsappLink.style.display = "none";
            }

            elements.reminderOutputBox.style.display = "block";
            elements.reminderModal.style.display = "flex";
        } catch (err) {
            showToast(err.message, "error");
        }
    }

    // --- Event Listeners ---
    function setupEventListeners() {
        // Tab Navigation
        if (elements.tabLedgerBtn) {
            elements.tabLedgerBtn.addEventListener("click", () => showView("home"));
        }
        if (elements.tabCollectionsBtn) {
            elements.tabCollectionsBtn.addEventListener("click", () => showView("collections"));
        }

        // Ask Feature
        if (elements.askForm) {
            elements.askForm.addEventListener("submit", handleAskSubmit);
        }

        // Collections Agent Feature
        if (elements.runCollectionsBtn) {
            elements.runCollectionsBtn.addEventListener("click", handleRunCollectionsReview);
        }
        if (elements.toggleTraceBtn) {
            elements.toggleTraceBtn.addEventListener("click", toggleTrace);
        }

        // Language Toggle
        elements.langToggleBtn.addEventListener("click", () => {
            currentLang = currentLang === "en" ? "ta" : "en";
            localStorage.setItem("kadai_khata_lang", currentLang);
            applyTranslations();
            renderCustomerList();
        });


        // Search Filter
        elements.customerSearchInput.addEventListener("input", () => {
            const hasVal = elements.customerSearchInput.value.trim().length > 0;
            elements.searchClearBtn.style.display = hasVal ? "flex" : "none";
            renderCustomerList();
        });

        elements.searchClearBtn.addEventListener("click", () => {
            elements.customerSearchInput.value = "";
            elements.searchClearBtn.style.display = "none";
            elements.customerSearchInput.focus();
            renderCustomerList();
        });

        // Transcription Form Submit
        elements.transcriptionForm.addEventListener("submit", (e) => {
            e.preventDefault();
            handleSentenceSubmit();
        });

        // Navigation
        elements.backToHomeBtn.addEventListener("click", () => {
            activeCustomer = null;
            showView("home");
            loadCustomers();
        });

        // Photo Upload Handlers
        if (elements.photoUploadBtn && elements.photoFileInput) {
            elements.photoUploadBtn.addEventListener("click", () => {
                elements.photoFileInput.click();
            });

            elements.photoFileInput.addEventListener("change", (e) => {
                const file = e.target.files && e.target.files[0];
                if (file) {
                    handlePhotoFileSelected(file);
                }
            });
        }

        if (elements.photoAckCheckbox) {
            elements.photoAckCheckbox.addEventListener("change", () => {
                updateConfirmAllState();
            });
        }

        elements.discardAllBtn.addEventListener("click", () => {
            currentDrafts = [];
            clearPhotoReviewUI();
            showView("home");
        });

        elements.confirmAllBtn.addEventListener("click", handleConfirmAll);

        // Reminder Modal
        elements.openReminderBtn.addEventListener("click", openReminderModal);
        elements.closeReminderModalBtn.addEventListener("click", closeReminderModal);
        elements.reminderModal.addEventListener("click", (e) => {
            if (e.target === elements.reminderModal) closeReminderModal();
        });
        elements.generateReminderBtn.addEventListener("click", handleGenerateReminder);
        elements.reminderCopyBtn.addEventListener("click", handleCopyMessage);

        // "Try these" Sample Chips (Fills input box only, does not auto-submit)
        document.querySelectorAll(".sample-chip").forEach(chip => {
            chip.addEventListener("click", () => {
                const text = chip.getAttribute("data-sentence");
                if (text && elements.sentenceInput) {
                    elements.sentenceInput.value = text;
                    elements.sentenceInput.focus();
                }
            });
        });

        // "Try a sample notebook page" Button
        if (elements.trySampleNotebookBtn) {
            elements.trySampleNotebookBtn.addEventListener("click", async () => {
                try {
                    elements.trySampleNotebookBtn.disabled = true;
                    const resp = await fetch("/static/samples/newpage3.jpeg");
                    if (!resp.ok) throw new Error("Could not load bundled sample notebook image.");
                    const blob = await resp.blob();
                    const sampleFile = new File([blob], "sample_notebook_page.jpeg", { type: "image/jpeg" });
                    handlePhotoFileSelected(sampleFile);
                } catch (err) {
                    showToast(err.message, "error");
                } finally {
                    elements.trySampleNotebookBtn.disabled = false;
                }
            });
        }

        // "How it works" Modal
        if (elements.howItWorksBtn && elements.howItWorksModal) {
            const openModal = () => {
                elements.howItWorksModal.style.display = "flex";
                elements.howItWorksBtn.setAttribute("aria-expanded", "true");
            };
            const closeModal = () => {
                elements.howItWorksModal.style.display = "none";
                elements.howItWorksBtn.setAttribute("aria-expanded", "false");
            };
            elements.howItWorksBtn.addEventListener("click", openModal);
            if (elements.closeHowItWorksBtn) {
                elements.closeHowItWorksBtn.addEventListener("click", closeModal);
            }
            elements.howItWorksModal.addEventListener("click", (e) => {
                if (e.target === elements.howItWorksModal) closeModal();
            });
        }
    }

    // --- Init ---
    function init() {
        applyTranslations();
        setupEventListeners();
        loadCustomers();
    }

    document.addEventListener("DOMContentLoaded", init);
})();
