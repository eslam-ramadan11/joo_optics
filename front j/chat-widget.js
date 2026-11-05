// Simple, self-contained FAQ chat widget focused on lens types. No backend
// call, no API key - pure keyword matching against a small knowledge base.
// Injects its own HTML/CSS-driven markup into every page that loads this
// script, so no page templates needed to be edited individually.

(function () {
    const WHATSAPP_URL = 'https://wa.me/201287178261';

    const KNOWLEDGE_BASE = [
        {
            id: 'standard',
            keywords: ['عادي', 'عادية', 'standard', 'شفاف', 'شفافه', 'أرخص', 'ارخص'],
            question: 'عدسات عادية شفافة (Standard)',
            answer:
                'العدسات العادية الشفافة هي الأساسية والأرخص سعرًا. بتصحح النظر بس من غير أي إضافات. السعر بيبدأ من 300 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'pg',
            keywords: ['pg', 'حماية 50', 'انعكاس', 'لمعان', 'وهج', 'لمعة'],
            question: 'عدسات PG',
            answer:
                'بتوفر حماية 50% من الأشعة الضارة. السعر بيبدأ من 350 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'bluecut',
            keywords: [
                'blue-cut', 'bluecut', 'blue cut', 'أزرق', 'الأشعة الزرقاء', 'كمبيوتر',
                'شاشة', 'شاشه', 'موبايل', 'لابتوب', 'شغل اونلاين',
            ],
            question: 'عدسات Blue-cut',
            answer:
                'بتحجب 100% من الأشعة الضارة. أنسب اختيار لو شغلك أونلاين أو بتقضي وقت طويل قدام الشاشة. السعر بيبدأ من 500 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'photogray',
            keywords: ['photogray', 'رمادي', 'رمادى', 'يتلون', 'يغمق', 'شمس', 'الشمس'],
            question: 'عدسات Photogray',
            answer:
                'بتتغير لونها للأسود تلقائيًا لما تتعرض للشمس، وترجع شفافة تاني جوه. السعر بيبدأ من 500 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'photobrown',
            keywords: ['photobrown', 'بني', 'بنى', 'بنية'],
            question: 'عدسات Photobrown',
            answer:
                'زي الـ Photogray بالظبط في الوظيفة، بس بتتحول للون البني بدل الأسود في الشمس. السعر بيبدأ من 500 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'multifocal',
            keywords: ['multifocal', 'ملتيفوكال', 'قراءة وبعد', 'بعيد وقريب'],
            question: 'عدسات Multifocal',
            answer:
                'عدسات للمشي والقراءة معًا - تصحح الرؤية القريبة والبعيدة في نفس العدسة. السعر بيبدأ من 1500 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'nightdrive',
            keywords: ['night drive', 'قيادة ليلية', 'سواقة بالليل', 'قيادة بالليل'],
            question: 'عدسات Night Drive',
            answer:
                'مصممة للرؤية والقيادة الليلية بوضوح أكتر. السعر بيبدأ من 750 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'antibreak',
            keywords: ['ضد الكسر', 'antibreak', 'مقاومة الكسر', 'كسر'],
            question: 'عدسات ضد الكسر',
            answer:
                'عدسات مقواة ضد الكسر، متوفرة كمان بتركيبات مع PG أو Blue-cut. السعر بيبدأ من 650 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'photogray-bluecut',
            keywords: ['photogray blue cut', 'photogray bluecut', 'photogray-blue cut', 'فوتوجراي بلو كت'],
            question: 'عدسات Photogray - Blue Cut',
            answer:
                'بتجمع بين التغيّر للأسود في الشمس وحماية Blue Cut من أشعة الشاشات. السعر بيبدأ من 900 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'bluecut-antibreak',
            keywords: ['blue cut ضد الكسر', 'bluecut ضد الكسر', 'blue-cut ضد الكسر'],
            question: 'عدسات Blue Cut ضد الكسر',
            answer:
                'عدسات Blue Cut مقواة ضد الكسر. السعر بيبدأ من 800 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'photogray-bluecut-antibreak',
            keywords: ['photogray blue cut ضد الكسر', 'photogray bluecut ضد الكسر', 'photogray-blue cut-ضد الكسر'],
            question: 'عدسات Photogray Blue Cut ضد الكسر',
            answer:
                'بتجمع Photogray وBlue Cut وكمان مقاومة للكسر. السعر بيبدأ من 2000 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'photogray-bluecut-night-drive',
            keywords: ['photogray blue cut night drive', 'photogray bluecut night drive', 'photogray-blue cut-night drive'],
            question: 'عدسات Photogray Blue Cut Night Drive',
            answer:
                'بتجمع Photogray وBlue Cut مع تحسين الرؤية في القيادة الليلية. السعر بيبدأ من 1500 جنيه وبيختلف حسب درجة النظر.',
        },
        {
            id: 'advanced-help',
            keywords: ['ساعدني اختار', 'مش عارف اختار', 'عدسات متقدمة', 'ترشيح عدسات'],
            question: 'مش عارف تختار؟',
            answer:
                'حاسبة العدسات في الصفحة الرئيسية فيها خيار "ساعدني في اختيار عدسات متقدمة" - بتسألك إيه استخدامك الأساسي (كمبيوتر، شمس، قيادة ليلية، ضد الكسر) وبترشحلك أنسب عدسة بـ3 مستويات أسعار (اقتصادية، الأفضل، premium).',
        },
        {
            id: 'compare',
            keywords: ['فرق', 'الفرق بين', 'مقارنة', 'افضل عدسة', 'أفضل عدسة', 'انهي عدسة', 'أي عدسة'],
            question: 'مقارنة بين الأنواع',
            answer:
                'عندنا 12 نوع أساسي من العدسات، السعر بيختلف حسب درجة نظرك (كل ما الدرجة أعلى، السعر يزيد شوية). أرخص نوع هو العدسات العادية الشفافة (من 300 جنيه)، وأغلاها Photogray Blue Cut ضد الكسر (من 2000 جنيه). جرب حاسبة العدسات في الصفحة الرئيسية عشان تشوف كل الأسعار مظبوطة على درجتك بالظبط.',
        },
        {
            id: 'tiers',
            keywords: ['ليه السعر مختلف', 'السعر بيتغير ليه', 'درجة النظر بتأثر', 'فئة السعر'],
            question: 'ليه سعر العدسة بيختلف من واحد للتاني؟',
            answer:
                'سعر أي نوع عدسة بيتحدد حسب درجة النظر بتاعتك (SPH و CYL) - كل ما الدرجة أعلى، التصنيع بيبقى أدق وده بيأثر على السعر. لو الدرجة عالية جدًا (SPH أكبر من 12 أو CYL أكبر من 6)، هنحولك تتكلم معانا على واتساب مباشرة عشان نديك سعر مناسب.',
        },
        {
            id: 'prescription',
            keywords: ['sph', 'cyl', 'axis', 'كشف', 'الكشف', 'اقرا الكشف', 'قراءة الكشف', 'روشتة', 'الروشتة', 'اقرا الروشتة', 'قراءة الروشتة'],
            question: 'قراءة الكشف (SPH / CYL / AXIS)',
            answer:
                'SPH (Sphere) هي درجة قصر أو طول النظر. CYL (Cylinder) هي درجة الاستجماتيزم إن وجد. AXIS هو اتجاه الاستجماتيزم بالدرجات (0-180). لو مش متأكد من قراءة كشفك، ارفع صورة منه وإحنا هنتأكد منها قبل التصنيع.',
        },
        {
            id: 'upload',
            keywords: ['ارفع', 'رفع', 'كشف جديد', 'اضيف كشف', 'روشتة جديدة', 'اضيف روشتة', 'upload prescription'],
            question: 'رفع كشف جديد',
            answer:
                'تقدر تدخل أرقام كشفك في "حاسبة العدسات" بالصفحة الرئيسية عشان تشوف الأسعار المتاحة، وترفع صورة الكشف الفعلية وانت بتكمل طلبك في صفحة الـ Checkout.',
        },
        {
            id: 'how-to-order',
            keywords: [
                'اطلب', 'أطلب', 'كيف اطلب', 'إزاي اطلب', 'عايز اطلب', 'طريقة الطلب',
                'how to order', 'order', 'checkout',
            ],
            question: 'إزاي أطلب من الموقع؟',
            answer:
                'اختار المنتج من صفحة المتجر واضغط "أضف إلى السلة"، وبعدين ادخل على السلة وكمّل الطلب (Checkout). هيطلب منك تختار عنوان الشحن، وتحدد هل محتاج عدسات طبية ولا لأ، وطريقة الدفع، وبعدها تأكيد الطلب.',
        },
        {
            id: 'prescription-vs-sunglasses',
            keywords: [
                'محتاج كشف', 'لازم كشف', 'لازم أرفع كشف', 'من غير كشف', 'بدون كشف',
                'محتاج روشتة', 'لازم روشتة', 'لازم أرفع روشتة', 'نظارة شمس عادية', 'من غير روشتة', 'بدون روشتة',
                'شنبر بس', 'عدسات طبية ولا لأ',
            ],
            question: 'هل لازم أرفع كشف مع كل طلب؟',
            answer:
                'لأ. وقت الـ Checkout هتلاقي سؤال "محتاج عدسات طبية؟" - لو جاوبت "لأ" (يعني نظارة شمس أو شنبر عادي من غير تصحيح نظر)، مش هيطلب منك كشف خالص. لو جاوبت "أيوه"، وقتها هتحتاج تختار كشف (أو ترفع واحد جديد) ونوع العدسة.',
        },
        {
            id: 'payment-methods',
            keywords: [
                'طرق الدفع', 'ادفع', 'أدفع', 'الدفع', 'كاش', 'فيزا', 'اونلاين', 'payment', 'pay',
            ],
            question: 'إيه طرق الدفع المتاحة؟',
            answer:
                'عندنا طريقتين: الدفع عند الاستلام (كاش)، أو الدفع أونلاين مباشرة بالكارت أو المحفظة الإلكترونية وقت الـ Checkout.',
        },
        {
            id: 'account',
            keywords: [
                'حسابي', 'بروفايل', 'سجل المشتريات', 'طلباتي', 'اعدادات', 'إعدادات', 'my account', 'profile',
            ],
            question: 'إيه اللي أقدر أعمله في "حسابي"؟',
            answer:
                'من صفحة "حسابي" تقدر: تعدل اسمك وإيميلك، تغيّر كلمة السر، تضيف/تحذف عناوين شحن، وتشوف سجل كل طلباتك السابقة وحالة كل طلب.',
        },
        {
            id: 'categories',
            keywords: [
                'اقسام', 'أقسام', 'تصنيفات', 'انواع النظارات', 'أنواع النظارات', 'categories',
            ],
            question: 'إيه أقسام المنتجات المتاحة؟',
            answer:
                'عندنا 5 أقسام: نظارات شمس رجالي، نظارات شمس حريمي، شنابر طبي رجالي، شنابر طبي حريمي، ونظارات أطفال. تقدر تفلتر بيهم من صفحة المتجر.',
        },
    ];

    const FALLBACK_ANSWER =
        'معنديش إجابة جاهزة للسؤال ده. جرب تسأل عن نوع عدسة، طريقة الطلب، الدفع، أو حسابك - أو تواصل معانا من صفحة "تواصل معنا" وهنرد عليك بنفسنا.';

    const SUGGESTED_QUESTIONS = [
        'إزاي أطلب من الموقع؟',
        'إيه طرق الدفع المتاحة؟',
        'هل لازم أرفع كشف مع كل طلب؟',
        'ايه هي عدسات Blue-cut؟',
    ];

    function normalize(text) {
        return (text || '').toLowerCase().trim();
    }

    function findAnswer(userText) {
        const normalized = normalize(userText);
        if (!normalized) return null;

        let best = null;
        let bestScore = 0;
        KNOWLEDGE_BASE.forEach((entry) => {
            let score = 0;
            entry.keywords.forEach((kw) => {
                if (normalized.includes(kw.toLowerCase())) {
                    score += kw.length;
                }
            });
            if (score > bestScore) {
                bestScore = score;
                best = entry;
            }
        });

        return best;
    }

    function escapeHtmlLocal(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function buildWidget() {
        const container = document.createElement('div');
        container.id = 'lens-chat-widget';
        container.innerHTML = `
            <a class="lens-whatsapp-toggle" href="${WHATSAPP_URL}" target="_blank" rel="noopener noreferrer" aria-label="تواصل معنا على واتساب" title="تواصل معنا على واتساب">
                <i class="fa-brands fa-whatsapp" aria-hidden="true"></i>
            </a>
            <button type="button" id="lens-chat-toggle" aria-label="محادثة Joo Optics">
                <span id="lens-chat-toggle-icon">💬</span>
            </button>
            <div id="lens-chat-panel" style="display:none;">
                <div id="lens-chat-header">
                    <span>Ask Joo Optics</span>
                    <button type="button" id="lens-chat-close" aria-label="إغلاق المحادثة">&times;</button>
                </div>
                <div id="lens-chat-messages"></div>
                <div id="lens-chat-suggestions"></div>
                <form id="lens-chat-form">
                    <input type="text" id="lens-chat-input" placeholder="اكتب نوع عدسة أو سؤالك..." aria-label="اكتب سؤالك" autocomplete="off">
                    <button type="submit">Send</button>
                </form>
            </div>
        `;
        document.body.appendChild(container);
        return container;
    }

    function addMessage(messagesEl, text, sender) {
        const bubble = document.createElement('div');
        bubble.className = `lens-chat-msg lens-chat-msg-${sender}`;
        bubble.innerHTML = escapeHtmlLocal(text).replace(/\n/g, '<br>');
        messagesEl.appendChild(bubble);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function respondTo(messagesEl, userText) {
        addMessage(messagesEl, userText, 'user');

        const match = findAnswer(userText);
        setTimeout(() => {
            if (match) {
                addMessage(messagesEl, `${match.question}\n\n${match.answer}`, 'bot');
            } else {
                addMessage(messagesEl, FALLBACK_ANSWER, 'bot');
            }
        }, 300);
    }

    function renderSuggestions(suggestionsEl, messagesEl, inputEl) {
        suggestionsEl.innerHTML = '';
        SUGGESTED_QUESTIONS.forEach((q) => {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'lens-chat-chip';
            chip.textContent = q;
            chip.addEventListener('click', () => {
                respondTo(messagesEl, q);
            });
            suggestionsEl.appendChild(chip);
        });
    }

    function init() {
        const container = buildWidget();
        const toggleBtn = container.querySelector('#lens-chat-toggle');
        const panel = container.querySelector('#lens-chat-panel');
        const closeBtn = container.querySelector('#lens-chat-close');
        const messagesEl = container.querySelector('#lens-chat-messages');
        const suggestionsEl = container.querySelector('#lens-chat-suggestions');
        const form = container.querySelector('#lens-chat-form');
        const input = container.querySelector('#lens-chat-input');

        let opened = false;

        toggleBtn.addEventListener('click', () => {
            const isOpen = panel.style.display !== 'none';
            panel.style.display = isOpen ? 'none' : 'flex';

            if (!isOpen && !opened) {
                opened = true;
                addMessage(
                    messagesEl,
                    'أهلاً! اسألني عن أنواع العدسات، طريقة الطلب، الدفع، أو حسابك. جرب واحدة من الأسئلة دي أو اكتب سؤالك:',
                    'bot'
                );
                renderSuggestions(suggestionsEl, messagesEl, input);
            }
        });

        closeBtn.addEventListener('click', () => {
            panel.style.display = 'none';
        });

        form.addEventListener('submit', (event) => {
            event.preventDefault();
            const text = input.value.trim();
            if (!text) return;
            respondTo(messagesEl, text);
            input.value = '';
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
