"""
小红书采集 - 共享基础模块
Config + BaseCrawler (浏览器/登录/反爬/拦截)
"""
import re, time, random, os, sys, json, csv, ctypes, traceback, requests
from datetime import datetime
from playwright.sync_api import sync_playwright

STEALTH_JS = """
// ====== L0: Navigator 核心属性 ======
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const proto = typeof PluginArray !== 'undefined' ? PluginArray.prototype : HTMLCollection.prototype;
        const arr = [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
            {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
        ];
        arr.item = i => arr[i] || null;
        arr.namedItem = n => arr.find(p => p.name === n) || null;
        arr.refresh = () => {};
        try { Object.setPrototypeOf(arr, proto); } catch(e) {}
        return arr;
    }
});
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
        const proto = typeof MimeTypeArray !== 'undefined' ? MimeTypeArray.prototype : HTMLCollection.prototype;
        const arr = [
            {type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format'},
            {type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format'},
        ];
        arr.item = i => arr[i] || null;
        arr.namedItem = n => arr.find(m => m.type === n) || null;
        try { Object.setPrototypeOf(arr, proto); } catch(e) {}
        return arr;
    }
});

// ====== L0: 屏幕/窗口属性 ======
Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth + 16});
Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 88});
Object.defineProperty(screen, 'width', {get: () => window.outerWidth + 360});
Object.defineProperty(screen, 'height', {get: () => window.outerHeight + 200});
Object.defineProperty(screen, 'colorDepth', {get: () => 24});
Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
Object.defineProperty(screen, 'availWidth', {get: () => screen.width - 40});
Object.defineProperty(screen, 'availHeight', {get: () => screen.height - 100});

// ====== L0: Chrome Runtime ======
if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) {
    window.chrome.runtime = {
        id: undefined,
        connect: function() { return {onMessage: {addListener: function(){}}, onDisconnect: {addListener: function(){}}, disconnect: function(){}, postMessage: function(){}}; },
        onConnect: {addListener: function(){}, removeListener: function(){}},
        onMessage: {addListener: function(){}, removeListener: function(){}},
        sendMessage: function() {},
        getManifest: function() { return {}; },
        getURL: function(p) { return p; },
    };
}
if (!window.chrome.csi) { window.chrome.csi = function() { return {loadTimes: function(){}}; }; }
if (!window.chrome.app) { window.chrome.app = {isInstalled: false}; }
if (!window.chrome.loadTimes) {
    window.chrome.loadTimes = function() {
        return {requestTime: Date.now()/1000-0.5, startLoadTime: Date.now()/1000-0.3,
                commitLoadTime: Date.now()/1000-0.1, finishDocumentLoadTime: Date.now()/1000,
                firstPaintTime: Date.now()/1000-0.05, firstPaintAfterLoadTime: 0,
                navigationType: 'Other', wasFetchedViaSpdy: true, wasNpnNegotiated: true,
                connectionInfo: 'http/1.1', npnNegotiatedProtocol: 'http/1.1'};
    };
}

// ====== L0: 硬件/语言 ======
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.'});
Object.defineProperty(navigator, 'productSub', {get: () => '20030107'});
Object.defineProperty(navigator, 'doNotTrack', {get: () => null});
Object.defineProperty(navigator, 'cookieEnabled', {get: () => true});

// ====== L0: Connection/Network ======
try {
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            effectiveType: '4g', rtt: 50, downlink: 10, saveData: false,
            onchange: null, type: 'ethernet'
        })
    });
} catch(e) {}

// ====== L0: Permissions API ======
try {
    const _origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = function(params) {
    if (params.name === 'notifications') {
        return Promise.resolve({state: 'prompt', onchange: null});
    }
    return _origQuery.call(this, params).then(result => {
        if (result.state === 'prompt') {
            try {
                Object.defineProperty(result, 'state', {value: 'granted'});
            } catch(e) {}
        }
        return result;
    });
} catch(e) {}

// ====== L0: Canvas 指纹噪声 (每次读取加微量噪声) ======
(function(){
    const noise = function(ctx) {
        if (ctx.canvas.width < 10 || ctx.canvas.height < 10) return;
        const imageData = ctx.getImageData(0, 0, ctx.canvas.width, ctx.canvas.height);
        for (let i=0; i < imageData.data.length; i+=4) {
            const r = Math.random();
            if (r < 0.002) {
                imageData.data[i] = Math.min(255, imageData.data[i] + (Math.random() > 0.5 ? 1 : -1));
            }
        }
        ctx.putImageData(imageData, 0, 0);
    };
    const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function() { noise(this.getContext('2d')); return _toDataURL.apply(this, arguments); };
    const _toBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function() { noise(this.getContext('2d')); return _toBlob.apply(this, arguments); };
})();

// ====== L0: WebGL 渲染器指纹 ======
try {
    const _getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'ANGLE (Microsoft, Microsoft Edge WebGL, Direct3D11 vs_5_0 ps_5_0, D3D11)';
        if (p === 37446) return 'Google Inc. (Microsoft)';
        return _getParam.call(this, p);
    };
} catch(e) {}
try {
    const _2getParam = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'ANGLE (Microsoft, Microsoft Edge WebGL, Direct3D11 vs_5_0 ps_5_0, D3D11)';
        if (p === 37446) return 'Google Inc. (Microsoft)';
        return _2getParam.call(this, p);
    };
} catch(e) {}

// ====== L0: AudioContext 指纹防御 ======
try {
    const _createOscillator = AudioContext.prototype.createOscillator;
    AudioContext.prototype.createOscillator = function() {
        const osc = _createOscillator.call(this);
        const _start = osc.start;
        osc.start = function() { return _start.call(this); };
        return osc;
    };
} catch(e) {}

// ====== L0: iframe contentWindow 检测防御 ======
try {
    const _getOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
    Object.getOwnPropertyDescriptor = function(obj, prop) {
        if (obj === HTMLIFrameElement.prototype && prop === 'contentWindow') {
            return undefined;
        }
        return _getOwnPropertyDescriptor.apply(this, arguments);
    };
} catch(e) {}

// ====== L0: Error stack trace 清理 ======
if (window.Error && Error.stackTraceLimit) {
    Error.stackTraceLimit = 30;
}

// ====== L0: Battery API 伪装 ======
try {
    navigator.getBattery = function() {
        return Promise.resolve({
            charging: true, chargingTime: 0, dischargingTime: Infinity,
            level: 0.85 + Math.random() * 0.1,
            onchargingchange: null, onchargingtimechange: null,
            ondischargingtimechange: null, onlevelchange: null,
            addEventListener: function(){}, removeEventListener: function(){}
        });
    };
} catch(e) {}

// ====== L0: Notification API ======
try {
    if (window.Notification) {
        Object.defineProperty(Notification, 'permission', {get: () => 'default'});
        const _requestPerm = Notification.requestPermission;
        Notification.requestPermission = function() {
            return Promise.resolve('default');
        };
    }
} catch(e) {}

// ====== L0: MediaDevices 伪装 ======
try {
    const _enumDevices = MediaDevices.prototype.enumerateDevices;
    MediaDevices.prototype.enumerateDevices = function() {
        return _enumDevices.call(this).then(devices => {
            return devices.filter(d => d.kind !== 'audiooutput' || Math.random() > 0.3);
        });
    };
} catch(e) {}

// ====== L0: Geolocation 伪装 ======
try {
    navigator.geolocation.getCurrentPosition = function(success, error) {
        success({
            coords: {
                latitude: 31.2304 + Math.random() * 0.01,
                longitude: 121.4737 + Math.random() * 0.01,
                accuracy: 20 + Math.random() * 30,
                altitude: null, altitudeAccuracy: null,
                heading: null, speed: null
            },
            timestamp: Date.now()
        });
    };
} catch(e) {}

// ====== L0: Font 指纹防御（限制字体枚举） ======
try {
    const _queryFonts = document.fonts.query;
    if (_queryFonts) {
        document.fonts.query = function() {
            return _queryFonts.call(document.fonts).then(function(fonts) {
                return fonts;
            });
        };
    }
} catch(e) {}

// ====== L0: rAF 时间噪声 ======
(function(){
    const _rAF = window.requestAnimationFrame;
    let jitter = 0;
    window.requestAnimationFrame = function(cb) {
        return _rAF.call(window, function(ts) {
            jitter += Math.random() * 2;
            cb(ts + jitter);
        });
    };
})();

// ====== L0: 阻止自动化检测 Script 注入 ======
Object.defineProperty(document, 'wasDiscarded', {get: () => false});
try {
    Object.defineProperty(window, 'external', {
        get: () => ({
            IsSearchProviderInstalled: function(){ return false; },
            AddSearchProvider: function(){},
        })
    });
} catch(e) {}

// ====== L0: 通用自动化标记清理 ======
delete window.__nightmare;
delete window.__selenium_unwrapped;
delete window.__webdriver_evaluate;
delete window.__driver_evaluate;
delete window.__webdriver_script_function;
delete window.__webdriver_script_func;
delete window.__webdriver_script_fn;
delete window.__fxdriver_evaluate;
delete window.__driver_unwrapped;
delete window.__webdriver_unwrapped;
delete window.__phantom;
delete window.callPhantom;
delete window._phantom;
delete window.__phantomas;
delete window.Buffer;
delete window.emit;
delete window.spawn;

// ====== L0: CDP / DevTools 深度清理 ======
delete window.__commandLineAPI;
delete window.__scopeEvents;
delete window.__inspector;
delete window.__crd;
delete window.chrome.debugger;
delete window.__nightmare;
try { Object.defineProperty(navigator, 'userAgentData', {get: () => undefined}); } catch(e) {}
// Console 快捷方式（DevTools 暴露的）
['$', '$$', '$x', '$0', '$_', '$1', '$2', '$3', '$4'].forEach(function(k) {
    try { delete window[k]; } catch(e) {}
});

// ====== L0: Performance API 伪装 ======
try {
    const _navEntry = performance.getEntriesByType('navigation')[0] || {};
    const _origGetEntries = performance.getEntriesByType;
    performance.getEntriesByType = function(type) {
        if (type === 'navigation') {
            return [Object.assign({}, _navEntry, {
                type: 'navigate', redirectCount: 0,
                transferSize: Math.floor(Math.random() * 5000) + 3000,
                decodedBodySize: Math.floor(Math.random() * 50000) + 20000,
                encodedBodySize: Math.floor(Math.random() * 20000) + 8000,
            })];
        }
        return _origGetEntries.call(this, type);
    };
    // 覆盖 performance.navigation (deprecated but still checked)
    try {
        Object.defineProperty(performance, 'navigation', {get: () => ({
            type: 0, redirectCount: 0
        })});
    } catch(e) {}
} catch(e) {}

// ====== L0: 补漏 Navigator 属性 ======
try {
    Object.defineProperty(navigator, 'userAgentData', {get: () => undefined});
} catch(e) {}
try {
    Object.defineProperty(navigator, 'mediaCapabilities', {
        get: () => ({
            decodingInfo: function() { return Promise.resolve({supported: true, smooth: true, powerEfficient: true}); },
            encodingInfo: function() { return Promise.resolve({supported: true, smooth: true, powerEfficient: true}); },
        })
    });
} catch(e) {}
try {
    Object.defineProperty(navigator, 'bluetooth', {
        get: () => ({
            getAvailability: function() { return Promise.resolve(false); },
            requestDevice: function() { return Promise.reject(new Error('Bluetooth not available')); },
            onavailabilitychanged: null,
        })
    });
} catch(e) {}
try {
    Object.defineProperty(navigator, 'usb', {
        get: () => ({
            getDevices: function() { return Promise.resolve([]); },
            requestDevice: function() { return Promise.reject(new Error('No device selected')); },
            onconnect: null, ondisconnect: null,
        })
    });
} catch(e) {}
try {
    Object.defineProperty(screen, 'orientation', {
        get: () => ({
            type: 'landscape-primary', angle: 0,
            onchange: null,
            lock: function() { return Promise.resolve(); },
            unlock: function() {},
        })
    });
} catch(e) {}
// 补充: navigator.keyboard (某些检测用)
try {
    Object.defineProperty(navigator, 'keyboard', {
        get: () => ({
            getLayoutMap: function() { return Promise.resolve(new Map()); },
            lock: function() {}, unlock: function() {},
            ongeometrychange: null,
        })
    });
} catch(e) {}

// ====== L0: localStorage 种子（假浏览历史） ======
(function() {
    try {
        const history = {
            'last_visit': Date.now() - Math.floor(Math.random() * 3600000),
            'recent_notes': [Math.random().toString(36).slice(2, 18), Math.random().toString(36).slice(2, 18)],
            'search_history': ['穿搭', '护肤', '美食'].sort(() => Math.random() - 0.5).slice(0, 2),
            'tab_preference': 'explore',
        };
        for (const [k, v] of Object.entries(history)) {
            if (!localStorage.getItem(k)) {
                localStorage.setItem(k, typeof v === 'string' ? v : JSON.stringify(v));
            }
        }
    } catch(e) {}
})();

// ====== L0: IntersectionObserver 伪装 ======
(function() {
    const _origIO = window.IntersectionObserver;
    const _seen = new WeakSet();
    window.IntersectionObserver = function(cb, opts) {
        const observer = new _origIO(function(entries, obs) {
            // 将所有条目标记为"可见+相交"
            for (const e of entries) {
                try { Object.defineProperty(e, 'isIntersecting', {value: true}); } catch(_) {}
                try { Object.defineProperty(e, 'intersectionRatio', {value: 0.6 + Math.random() * 0.4}); } catch(_) {}
                try { Object.defineProperty(e, 'isVisible', {value: true}); } catch(_) {}
                _seen.add(e.target);
            }
            cb(entries, obs);
        }, opts);
        return observer;
    };
    window.IntersectionObserver.prototype = _origIO.prototype;
})();

// ====== L0: requestIdleCallback 伪装 ======
if (!window.requestIdleCallback) {
    window.requestIdleCallback = function(cb, opts) {
        const delay = (opts && opts.timeout) ? opts.timeout : Math.floor(Math.random() * 500) + 50;
        return setTimeout(function() {
            cb({didTimeout: false, timeRemaining: function() { return 15 + Math.random() * 35; }});
        }, delay);
    };
    window.cancelIdleCallback = function(id) { clearTimeout(id); };
}

// ====== L0: Service Worker 伪装 ======
try {
    Object.defineProperty(navigator, 'serviceWorker', {
        get: () => ({
            controller: null,
            ready: new Promise(() => {}),
            register: function() { return Promise.resolve({unregister: function(){}}); },
            getRegistration: function() { return Promise.resolve(undefined); },
            getRegistrations: function() { return Promise.resolve([]); },
            oncontrollerchange: null, onmessage: null,
        })
    });
} catch(e) {}

// ====== L0: screenX/focus/失焦补漏 ======
(function(){
    var _ri = function(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; };
    try { Object.defineProperty(window, 'screenX', {get: function(){return _ri(-8, 0);}}); } catch(e){}
    try { Object.defineProperty(window, 'screenLeft', {get: function(){return window.screenX;}}); } catch(e){}
    try { Object.defineProperty(window, 'screenY', {get: function(){return _ri(20, 50);}}); } catch(e){}
    try { Object.defineProperty(window, 'screenTop', {get: function(){return window.screenY;}}); } catch(e){}
})();
(function(){
    var _hasFocus = Document.prototype.hasFocus;
    var _blurUntil = 0;
    Document.prototype.hasFocus = function() {
        if (Date.now() < _blurUntil) return false;
        return _hasFocus.call(this);
    };
    function _scheduleBlur() {
        var delay = Math.floor(Math.random() * 90000) + 30000;
        setTimeout(function() {
            _blurUntil = Date.now() + Math.floor(Math.random() * 4000) + 1000;
            _scheduleBlur();
        }, delay);
    }
    _scheduleBlur();
})();
// ====== L0: Performance longtask 伪装 ======
try {
    var _ltGetEntries = performance.getEntriesByType;
    performance.getEntriesByType = function(type) {
        if (type === 'longtask') return [];
        return _ltGetEntries.call(this, type);
    };
} catch(e) {}
// ====== L0: getClientRects 微小噪声 ======
try {
    var _origGCR = Element.prototype.getClientRects;
    Element.prototype.getClientRects = function() {
        var rects = _origGCR.call(this);
        if (rects && rects.length > 0 && Math.random() < 0.01) {
            try {
                var r = rects[0];
                Object.defineProperty(r, 'width', {get: function(){return r.right - r.left + (Math.random() > 0.5 ? 0.5 : -0.5);}});
            } catch(e){}
        }
        return rects;
    };
} catch(e) {}
"""


def _app_dir():
    """exe打包后取exe所在目录，开发时取脚本目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

class Config:
    def __init__(self):
        base = _app_dir()
        self.config_file = os.path.join(base, "config.json")
        self.keyword = "穿搭"
        self.target = "评论"
        self.likes_min = 5000
        self.likes_max = None
        self.fans_min = 50000
        self.fans_max = None
        self.max_pages = 2
        self.bio_scroll = True
        self.comment_likes_min = 1000
        self.comment_likes_max = None
        self.max_comment_pages = 3
        self.sort_by = "综合"
        self.note_type = "不限"
        self.publish_time = "不限"
        self.search_scope = "不限"
        self.search_location = "不限"
        self.cookie_file = os.path.join(base, "cookies.json")
        self.output_base = os.path.join(base, "output")
        self.user_data = os.path.join(base, "browser_data")
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
        # IP轮换设置
        self.ip_rotate_enabled = False
        self.ip_rotate_method = "pppoe"   # pppoe / proxy
        self.ip_rotate_frequency = "task"  # task / interval
        self.pppoe_name = "宽带连接"
        # 代理设置（ip_rotate_method=proxy 时使用）
        self.proxy_type = "http"          # http / socks5
        self.proxy_host = ""
        self.proxy_port = 1080
        self.proxy_username = ""
        self.proxy_password = ""
        # 断点续采（默认关闭，开启后增加写盘频率可能引起风控注意）
        self.checkpoint_enabled = False
        # 极速模式（默认关闭，跳过所有防检测延迟，封号风险极高）
        self.turbo_mode = False
        self._load()

    def save(self):
        fields = ['keyword', 'target', 'likes_min', 'likes_max', 'fans_min', 'fans_max',
                  'max_pages', 'bio_scroll', 'comment_likes_min', 'comment_likes_max',
                  'max_comment_pages', 'output_base',
                  'sort_by', 'note_type', 'publish_time', 'search_scope', 'search_location',
                  'ip_rotate_enabled', 'ip_rotate_method', 'ip_rotate_frequency',
                  'pppoe_name', 'proxy_type', 'proxy_host', 'proxy_port',
                  'proxy_username', 'proxy_password', 'checkpoint_enabled', 'turbo_mode']
        data = {k: getattr(self, k) for k in fields}
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [Config] 保存失败: {e}")

    def _load(self):
        if not os.path.exists(self.config_file):
            return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(self, k):
                    setattr(self, k, v)
        except:
            pass


class TaskSlot:
    """独立任务槽，持有自己的目标+筛选条件"""
    def __init__(self, slot_id):
        self.slot_id = slot_id
        self.target = None        # "作品"/"博主"/"评论"/None
        self.keyword = ""
        self.likes_min = 5000
        self.likes_max = None
        self.fans_min = 50000
        self.fans_max = None
        self.comment_likes_min = 1000
        self.comment_likes_max = None
        self.max_pages = 2
        self.max_comment_pages = 3
        self.sort_by = "综合"
        self.note_type = "不限"
        self.publish_time = "不限"
        self.search_scope = "不限"

    def fields_for_target(self):
        """根据当前target返回可编辑项: [(key, label, current_value, choices_or_None)]"""
        items = [
            ("target",     "目标类型",   self.target,
             ["作品", "博主", "评论"]),
            ("keyword",    "关键词",     self.keyword,
             None),
        ]
        if self.target == "作品":
            items += [
                ("likes_min",     "点赞下限",   self.likes_min,     None),
                ("likes_max",     "点赞上限",   self.likes_max or "无上限", None),
                ("sort_by",       "排序依据",   self.sort_by,
                 ["综合", "最新", "最多点赞", "最多评论", "最多收藏"]),
                ("publish_time",  "发布时间",   self.publish_time,
                 ["不限", "一天内", "一周内", "半年内"]),
                ("search_scope",  "搜索范围",   self.search_scope,
                 ["不限", "已看过", "未看过", "已关注"]),
                ("max_pages",     "最大页数",   self.max_pages,     None),
            ]
        elif self.target == "博主":
            items += [
                ("fans_min",      "粉丝下限",   self.fans_min,      None),
                ("fans_max",      "粉丝上限",   self.fans_max or "无上限", None),
                ("max_pages",     "最大页数",   self.max_pages,     None),
            ]
        elif self.target == "评论":
            items += [
                ("comment_likes_min", "评论点赞下限", self.comment_likes_min, None),
                ("comment_likes_max", "评论点赞上限", self.comment_likes_max or "无上限", None),
                ("max_comment_pages", "评论翻页数",   self.max_comment_pages,  None),
            ]
        return items

    def to_config(self):
        """转为Config对象，传给爬虫用"""
        c = Config()
        c.target = self.target
        c.keyword = self.keyword
        c.likes_min = self.likes_min
        c.likes_max = self.likes_max
        c.fans_min = self.fans_min
        c.fans_max = self.fans_max
        c.comment_likes_min = self.comment_likes_min
        c.comment_likes_max = self.comment_likes_max
        c.max_pages = self.max_pages
        c.max_comment_pages = self.max_comment_pages
        c.sort_by = self.sort_by
        c.note_type = self.note_type
        c.publish_time = self.publish_time
        c.search_scope = self.search_scope
        c.output_base = Config().output_base  # 全局输出目录
        return c

    def one_line(self):
        """单行摘要，用于主面板"""
        if not self.target:
            return f"任务{self.slot_id}: [空] 未配置"
        parts = [f"任务{self.slot_id}: [{self.target}] {self.keyword}"]
        if self.target == "作品":
            parts.append(f"赞≥{self.likes_min}" + (f"~{self.likes_max}" if self.likes_max else ""))
            parts.append(f"{self.max_pages}页")
            parts.append(f"排序:{self.sort_by}")
            if self.publish_time != "不限":
                parts.append(f"时间:{self.publish_time}")
            if self.search_scope != "不限":
                parts.append(f"范围:{self.search_scope}")
        elif self.target == "博主":
            parts.append(f"粉丝≥{self.fans_min}" + (f"~{self.fans_max}" if self.fans_max else ""))
            parts.append(f"{self.max_pages}页")
        elif self.target == "评论":
            parts.append(f"评赞≥{self.comment_likes_min}"
                         + (f"~{self.comment_likes_max}" if self.comment_likes_max else ""))
            parts.append(f"{self.max_comment_pages}页")
        return "  ".join(parts)

    def to_dict(self):
        return {
            'slot_id': self.slot_id,
            'target': self.target,
            'keyword': self.keyword,
            'likes_min': self.likes_min, 'likes_max': self.likes_max,
            'fans_min': self.fans_min, 'fans_max': self.fans_max,
            'comment_likes_min': self.comment_likes_min, 'comment_likes_max': self.comment_likes_max,
            'max_pages': self.max_pages, 'max_comment_pages': self.max_comment_pages,
            'sort_by': self.sort_by, 'note_type': self.note_type,
            'publish_time': self.publish_time, 'search_scope': self.search_scope,
        }

    @staticmethod
    def from_dict(data):
        s = TaskSlot(data['slot_id'])
        for k in ['target', 'keyword', 'likes_min', 'likes_max', 'fans_min', 'fans_max',
                  'comment_likes_min', 'comment_likes_max', 'max_pages', 'max_comment_pages',
                  'sort_by', 'note_type', 'publish_time', 'search_scope']:
            if k in data:
                setattr(s, k, data[k])
        return s


class IpRotator:
    """IP 轮换 — 支持 PPPoE 拨号换 IP"""
    def __init__(self, config):
        self.cfg = config
        self._last_ip = None

    def get_current_ip(self):
        """获取当前公网 IP"""
        try:
            import urllib.request
            r = urllib.request.urlopen("https://api.ipify.org", timeout=10)
            return r.read().decode().strip()
        except:
            return None

    def rotate(self):
        """执行 IP 轮换"""
        if not self.cfg.ip_rotate_enabled:
            return True
        old_ip = self.get_current_ip()
        if self.cfg.ip_rotate_method == "pppoe":
            ok = self._pppoe_rotate()
        elif self.cfg.ip_rotate_method == "proxy":
            ok = True  # 代理模式下由代理服务器自动轮换
        else:
            return True
        if ok:
            new_ip = self.get_current_ip()
            if new_ip and new_ip != old_ip:
                print(f"  [IP] 轮换成功: {old_ip} → {new_ip}")
                self._last_ip = new_ip
                return True
            elif new_ip == old_ip:
                print(f"  [IP] 轮换后IP未变 ({old_ip}), 等待30s后重试...")
                time.sleep(30)
                return self.rotate()
        print(f"  [IP] 轮换失败, 继续使用当前IP")
        return False

    def _pppoe_rotate(self):
        """通过 rasdial 断开/重拨 PPPoE"""
        name = self.cfg.pppoe_name
        print(f"  [IP] 断开拨号 '{name}'...")
        r1 = os.system(f'rasdial "{name}" /disconnect 2>nul')
        time.sleep(random.uniform(5, 8))
        print(f"  [IP] 重新拨号 '{name}'...")
        r2 = os.system(f'rasdial "{name}" 2>nul')
        time.sleep(random.uniform(3, 5))
        return r2 == 0 or r1 == 0  # 断开/重拨任一成功就算OK


class RateLimiter:
    """并发控制 — 限制同时下载数"""
    def __init__(self, max_concurrent=10):
        import threading
        self._sem = threading.BoundedSemaphore(max_concurrent)

    def acquire(self):
        self._sem.acquire()

    def release(self):
        self._sem.release()


class CheckpointManager:
    """断点续采 — 页级保存进度，崩溃后可跳过已完成页"""
    def __init__(self, out_dir, enabled=True):
        self.enabled = enabled
        self.path = os.path.join(out_dir, "_checkpoint.json") if out_dir else None
        self.data = self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"completed_pages": [], "completed_note_ids": [],
                "current_page": 0, "stage": "init", "scraped_user_ids": []}

    def save(self):
        if not self.enabled or not self.path:
            return
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f)
        except:
            pass

    def mark_page_done(self, page_num):
        if page_num not in self.data["completed_pages"]:
            self.data["completed_pages"].append(page_num)

    def is_page_done(self, page_num):
        return page_num in self.data["completed_pages"]

    def mark_note_done(self, note_id):
        if note_id not in self.data["completed_note_ids"]:
            self.data["completed_note_ids"].append(note_id)

    def is_note_done(self, note_id):
        if note_id in self.data["completed_note_ids"]:
            return True
        if self.path:
            import glob as _glob
            pattern = os.path.join(os.path.dirname(self.path), "posts", f"*_{note_id}")
            return bool(_glob.glob(pattern))
        return False

    def set_page(self, n):
        self.data["current_page"] = n

    def set_stage(self, s):
        self.data["stage"] = s


class BaseCrawler:
    def __init__(self, config):
        self.config = config
        self.captured_responses = []
        self.comment_responses = []
        self.out_dir = ""
        self._shared_page = None
        self._shared_context = None
        self._rate_limited = False
        self._forbidden = False
        self._consecutive_errors = 0

    def run_with_page(self, page, context):
        """用外部提供的page/context运行，不管理浏览器生命周期"""
        self._shared_page = page
        self._shared_context = context
        self._setup_output_dir()
        print("=" * 60)
        print(f"  小红书采集 - {self.config.target}")
        print(f"  关键词: {self.config.keyword}")
        print(f"  输出: {self.out_dir}")
        print("=" * 60)
        self._run_impl()

    # ── 反爬 L1: 贝塞尔曲线鼠标（带微抖动） ──
    def _human_mouse_move(self, page, tx, ty, steps=None, jitter=True):
        """贝塞尔曲线 + 微抖动，模拟真人手抖"""
        if self.config.turbo_mode:
            return
        if steps is None:
            steps = random.randint(15, 30)
        sx, sy = random.randint(300, 800), random.randint(300, 600)
        cx1 = sx + random.randint(-100, 100)
        cy1 = sy + random.randint(-100, 100)
        cx2 = tx + random.randint(-80, 80)
        cy2 = ty + random.randint(-80, 80)
        for i in range(steps + 1):
            t = i / steps
            x = (1-t)**3 * sx + 3*(1-t)**2*t * cx1 + 3*(1-t)*t**2 * cx2 + t**3 * tx
            y = (1-t)**3 * sy + 3*(1-t)**2*t * cy1 + 3*(1-t)*t**2 * cy2 + t**3 * ty
            if jitter and random.random() < 0.3:
                x += random.randint(-2, 2)
                y += random.randint(-2, 2)
            page.mouse.move(x, y)
            # 行程中段慢、两端快
            mid = abs(t - 0.5)
            delay = random.uniform(0.003, 0.015) + mid * 0.008
            time.sleep(delay)

    # ── 反爬 L2: 多级随机停顿（正态分布，集中在中值附近） ──
    def _human_pause(self, min_t=0.3, max_t=1.5, long_chance=0.06):
        """分级停顿：短(正态)常态，中(3-8s)偶尔，长(10-25s)罕见"""
        if self.config.turbo_mode:
            if long_chance > 0.1:
                return  # 中长停顿直接跳过
            time.sleep(0.05)  # 短停顿只留 50ms
            return
        hour = datetime.now().hour
        if hour < 7 or hour >= 23:
            # 深夜/凌晨：正常用户不太活跃，降速
            min_t *= random.uniform(1.5, 2.0)
            max_t *= random.uniform(1.5, 2.0)
            long_chance *= 2.5
        r = random.random()
        if r < long_chance:
            t = random.uniform(10, 25)
            print(f"    [仿生长停顿 {t:.0f}s]")
        elif r < 0.15:
            t = random.uniform(3, 8)
            print(f"    [仿生中停顿 {t:.0f}s]")
        else:
            mu = (min_t + max_t) / 2.0
            sigma = (max_t - min_t) / 3.0
            t = max(min_t, min(max_t, random.gauss(mu, sigma)))
        time.sleep(t)

    # ── 反爬: P0 无目的鼠标飘移（模拟看屏幕边缘/进度条） ──
    def _idle_mouse_wander(self, page, chance=0.35):
        """无目的飘移到屏幕边缘再回来，模拟用户无意识鼠标活动"""
        if self.config.turbo_mode or random.random() > chance:
            return
        edge_x = random.choice([random.randint(0, 80), random.randint(850, 960)])
        edge_y = random.randint(100, 800)
        self._human_mouse_move(page, edge_x, edge_y, jitter=True)
        time.sleep(random.uniform(0.3, 0.8))
        self._human_mouse_move(page, random.randint(300, 700), random.randint(300, 600), jitter=True)

    # ── 反爬: P0 假阅读中断（长停留+鼠标活动，打断行为节奏） ──
    def _occasional_long_read(self, page, step_index):
        """每3-7步插入长停留，模拟读到感兴趣内容"""
        if self.config.turbo_mode:
            return
        if step_index % random.randint(3, 7) != 0:
            return
        if random.random() < 0.55:
            return
        t = random.uniform(6, 20)
        print(f"    [假阅读 {t:.0f}s]")
        moves = random.randint(2, 4)
        for _ in range(moves):
            self._idle_mouse_wander(page, chance=1.0)
            time.sleep(t / moves * 0.4)
        page.mouse.move(random.randint(300, 600), random.randint(300, 500))
        time.sleep(t * 0.3)

    # ── 反爬 L3: 仿生点击（随机偏移+前摇） ──
    def _human_click(self, page, selector, timeout=10000):
        """先移到元素（带偏移），短暂"看"一下，再点击"""
        if self.config.turbo_mode:
            page.locator(selector).first.click(timeout=timeout)
            return
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=timeout)
            box = el.bounding_box()
            if box:
                # 随机偏移（不精确点在中心）
                ox = box['x'] + box['width'] * random.uniform(0.2, 0.8)
                oy = box['y'] + box['height'] * random.uniform(0.3, 0.7)
                self._human_mouse_move(page, ox, oy)
                time.sleep(random.uniform(0.1, 0.4))
                page.mouse.click(ox, oy)
            else:
                el.click(timeout=timeout)
        except:
            pass

    # ── 反爬 L4: 仿生滚动（快慢交替+回滚+扫读） ──
    def _human_scroll(self, page, distance=None, deep_read=0.25):
        """小步长、回弹、阅读停顿、偶尔深读（发现感兴趣内容）"""
        if self.config.turbo_mode:
            page.mouse.wheel(0, distance or 600)
            return
        if distance is None:
            distance = random.randint(200, 600)
        direction = 1 if distance > 0 else -1
        abs_dist = abs(distance)
        remaining = abs_dist
        while remaining > 0:
            step = min(random.randint(40, 120), remaining)
            page.mouse.wheel(0, step * direction)
            remaining -= step
            time.sleep(random.uniform(0.03, 0.12))
        if random.random() < 0.25:
            page.mouse.wheel(0, random.randint(-80, -20))
            time.sleep(random.uniform(0.1, 0.3))
        r = random.random()
        if r < deep_read:
            t = max(3.0, min(12.0, random.gauss(6.5, 2.5)))
            time.sleep(t)
        elif r < 0.5:
            time.sleep(random.uniform(0.8, 3.0))

    # ── 反爬 L5: 验证检测+恢复（指数退避，最多5次） ──
    def _check_and_handle_verification(self, page):
        if not hasattr(self, '_captcha_retries'):
            self._captcha_retries = 0
        try:
            detected = False
            for sel in ['.captcha', '[class*="captcha"]', '[class*="slider"]',
                        '[class*="verify"]', '[class*="verification"]',
                        'iframe[src*="captcha"]']:
                if page.locator(sel).count() > 0:
                    detected = True
                    break
            if not detected:
                for sel in ['[class*="modal"]', '[class*="dialog"]', '[class*="overlay"]']:
                    el = page.locator(sel).first
                    if el.count() > 0:
                        try:
                            text = el.inner_text()
                            if any(kw in text for kw in ['验证', '滑动', 'security', 'captcha', '扫码']):
                                detected = True
                                break
                        except:
                            pass
            if detected:
                if self._captcha_retries >= 5:
                    print("  [验证] 已达最大重试(5次), 放弃")
                    return False
                wait = 2 ** self._captcha_retries * 15
                self._captcha_retries += 1
                print(f"  [验证] 第{self._captcha_retries}次, 等待{wait}s后重试...")
                time.sleep(wait)
                page.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(3, 5))
                return True
            self._captcha_retries = 0
        except:
            pass
        return False

    # ── 预判降温：连续无新数据时主动降速，避免触发XHS限流 ──
    # ── 任务间穿插：轻量浏览打破"搜索→采集→搜索"的规律 ──
    def _casual_browse(self, page):
        """采集任务之间穿插的轻量浏览（多类型，打破规律）"""
        if self.config.turbo_mode:
            return
        if random.random() < 0.4:
            return
        mode = random.choice(['explore', 'scan'])
        try:
            if mode == 'scan':
                print("  [穿插] 快速刷发现页...")
                page.goto("https://www.xiaohongshu.com/explore",
                          wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(1.0, 2.0))
                for _ in range(random.randint(3, 5)):
                    self._human_scroll(page, random.randint(400, 800), deep_read=0.15)
                    self._human_pause(0.3, 1.0)
                # 扫到底后往回翻（模仿翻回去重看）
                if random.random() < 0.5:
                    try:
                        page.evaluate("window.scrollBy(0, -600)")
                        self._human_mouse_move(page, random.randint(200, 700), random.randint(200, 600))
                        time.sleep(random.uniform(1.0, 2.5))
                    except:
                        pass
            else:
                print("  [穿插] 浏览推荐流...")
                page.goto("https://www.xiaohongshu.com/explore",
                          wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(1.0, 2.5))
                for _ in range(random.randint(2, 4)):
                    self._human_scroll(page, random.randint(300, 700), deep_read=0.35)
                    self._human_pause(0.5, 2.0)
            print("  [穿插] 完成")
        except Exception as e:
            print(f"  [穿插] 跳过 ({e})")

    def _cooldown_if_stale(self, stale_count, threshold=6):
        """连续stale次无新数据，主动长休息（正态分布均值附近）"""
        if self.config.turbo_mode:
            return False
        if stale_count >= threshold:
            t = max(10.0, min(60.0, random.gauss(30.0, 12.0)))
            print(f"  [预判降温] 连续{stale_count}次无新数据, 主动休息 {t:.0f}s")
            time.sleep(t)
            return True
        return False

    def _get_session(self):
        """获取 requests Session（自动配代理）"""
        if not hasattr(self, '_session') or self._session is None:
            self._session = requests.Session()
            if self.config.ip_rotate_enabled and self.config.ip_rotate_method == "proxy" and self.config.proxy_host:
                proto = "socks5" if self.config.proxy_type == "socks5" else self.config.proxy_type
                proxy_url = f"{proto}://{self.config.proxy_host}:{self.config.proxy_port}"
                self._session.proxies = {"http": proxy_url, "https": proxy_url}
                if self.config.proxy_username:
                    import base64 as _b64
                    up = f"{self.config.proxy_username}:{self.config.proxy_password}"
                    self._session.headers["Proxy-Authorization"] = f"Basic {_b64.b64encode(up.encode()).decode()}"
        return self._session

    def _setup_output_dir(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_kw = re.sub(r'[\\/:*?"<>|]', '', self.config.keyword)
        self.out_dir = os.path.join(self.config.output_base, f"{safe_kw}_{self.config.target}_{ts}")
        os.makedirs(self.out_dir, exist_ok=True)
        self.checkpoint = CheckpointManager(
            self.out_dir, enabled=self.config.checkpoint_enabled)

    # ── 拦截 ──
    def _handle_search_route(self, route):
        route.continue_()

    def _handle_search_response(self, response):
        status = response.status
        if status == 429:
            self._rate_limited = True
            self._consecutive_errors += 1
            delay = min(2 ** self._consecutive_errors * 5, 120)
            print(f"  [!] HTTP 429 限流, 建议等待 {delay}s")
            return
        if status == 403:
            self._forbidden = True
            print(f"  [!] HTTP 403 禁止访问")
            return
        if status in (502, 503):
            self._consecutive_errors += 1
            print(f"  [!] HTTP {status} 服务器错误")
            return
        if status != 200:
            return
        self._consecutive_errors = 0
        req = response.request
        url = req.url
        if req.method == 'POST':
            try:
                data = response.json()
                if not data or not isinstance(data, dict):
                    return
                items = data.get('data', {}).get('items', [])
                if not items:
                    items = data.get('data', {}).get('user_list', [])
                if not items:
                    items = data.get('data', {}).get('list', [])
                if not items and isinstance(data.get('data'), list):
                    items = data['data']
                if items:
                    pn = 0
                    try:
                        pn = json.loads(req.post_data).get('page', 0)
                    except:
                        pass
                    self.captured_responses.append({'page': pn, 'items': items, 'url': url})
                cmts = data.get('data', {}).get('comments', [])
                if cmts:
                    self.comment_responses.extend(cmts)
            except:
                pass

    # ── 安全导航 ──
    def _goto_safe(self, page, url, **kwargs):
        """goto前随机鼠标飘移 + Referrer链模拟 + 后检查验证"""
        self._human_mouse_move(page, random.randint(200, 900), random.randint(150, 600), jitter=False)
        time.sleep(random.uniform(0.15, 0.45))
        # 搜索页先跳首页建立 Referrer 链（极速模式跳过）
        if not self.config.turbo_mode and 'search_result' in url and random.random() < 0.7:
            current = page.url
            if 'xiaohongshu.com' not in current:
                page.goto("https://www.xiaohongshu.com/explore",
                          wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(0.8, 2.0))
        page.goto(url, **kwargs)
        self._human_pause(0.5, 2.0)
        self._check_and_handle_verification(page)

    # ── Session Warmup: 模拟真人浏览行为后再工作 ──
    def _session_warmup(self, page):
        """浏览首页→自然滚动→随机停留，降低'直达搜索'的机器人特征"""
        if self.config.turbo_mode:
            return
        if random.random() < 0.08:
            return  # 8% 跳过（闲鱼版经验值，比原来30%更积极）
        try:
            print("  [预热] 模拟浏览首页...")
            self._goto_safe(page, "https://www.xiaohongshu.com/explore",
                          wait_until="domcontentloaded", timeout=45000)
            time.sleep(random.uniform(2.0, 4.0))
            # 随机滚动 3-6 次（比原来多）
            for _ in range(random.randint(3, 6)):
                self._human_mouse_move(page, random.randint(200, 900), random.randint(200, 700))
                self._human_scroll(page, random.randint(300, 800))
                self._human_pause(0.5, 2.5)
            # 点一个卡片，进去看几秒再出来
            if random.random() < 0.55:
                try:
                    cards = page.locator('[class*="note-item"], [class*="feeds-item"], section a[href*="explore"]')
                    if cards.count() > 0:
                        idx = random.randint(0, min(cards.count() - 1, 10))
                        box = cards.nth(idx).bounding_box()
                        if box:
                            cx = box['x'] + box['width'] * random.uniform(0.3, 0.7)
                            cy = box['y'] + box['height'] * random.uniform(0.3, 0.7)
                            self._human_mouse_move(page, cx, cy)
                            self._human_pause(0.5, 1.5)
                            page.mouse.click(cx, cy)
                            print("  [预热] 浏览笔记...")
                            time.sleep(random.uniform(2.0, 5.0))
                            for _ in range(random.randint(1, 4)):
                                self._human_scroll(page, random.randint(200, 500))
                                self._human_pause(1.0, 3.0)
                            page.go_back(wait_until="domcontentloaded", timeout=15000)
                            time.sleep(random.uniform(1.0, 2.0))
                except:
                    pass
            # 模拟键盘 Home 回到顶部（自然的搜索前准备动作）
            page.keyboard.press("Home")
            time.sleep(random.uniform(0.3, 0.6))
            print("  [预热] 完成")
        except Exception as e:
            print(f"  [预热] 跳过 ({e})")

    # ── 键盘搜索：回首页 → 键盘输入 → 回车，比URL导航更拟真 ──
    def _search_via_keyboard(self, page, keyword, max_retries=2):
        """回到首页，定位搜索框→键盘输入→回车，模仿真人操作"""
        for attempt in range(max_retries):
            try:
                # 确保在首页
                if "xiaohongshu.com/explore" not in page.url:
                    self._goto_safe(page, "https://www.xiaohongshu.com/explore",
                                  wait_until="domcontentloaded", timeout=30000)
                    time.sleep(random.uniform(1.5, 3.0))
                else:
                    page.keyboard.press("Home")
                    time.sleep(random.uniform(0.3, 0.6))
                # 找搜索框
                search_input = None
                for sel in ['input[placeholder*="搜索"]', 'input[class*="search"]',
                            '[class*="search"] input', '[class*="search-box"] input']:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=1500):
                            search_input = el
                            break
                    except:
                        continue
                if not search_input:
                    # 尝试 role searchbox
                    try:
                        search_input = page.get_by_role("searchbox").first
                        if not search_input.is_visible(timeout=1000):
                            search_input = None
                    except:
                        pass
                if not search_input:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    # 兜底：直接用URL导航
                    print("  [键盘搜索] 找不到搜索框，回退URL导航")
                    return False
                # 点击搜索框
                search_input.scroll_into_view_if_needed()
                time.sleep(random.uniform(0.3, 0.5))
                box = search_input.bounding_box()
                if box:
                    sx = box['x'] + box['width'] * random.uniform(0.2, 0.6)
                    sy = box['y'] + box['height'] * random.uniform(0.3, 0.7)
                    self._human_mouse_move(page, sx, sy)
                    time.sleep(random.uniform(0.1, 0.3))
                    page.mouse.click(sx, sy)
                else:
                    search_input.click(timeout=3000)
                time.sleep(random.uniform(0.2, 0.5))
                # 清空 + 键盘输入
                page.keyboard.press("Control+a")
                time.sleep(random.uniform(0.1, 0.2))
                page.keyboard.press("Backspace")
                time.sleep(random.uniform(0.15, 0.3))
                page.keyboard.type(keyword, delay=random.randint(60, 180))
                time.sleep(random.uniform(0.3, 0.7))
                page.keyboard.press("Enter")
                time.sleep(random.uniform(2.0, 3.5))
                # 等搜索结果页加载
                try:
                    page.wait_for_url("**/search_result**", timeout=10000)
                except:
                    pass
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except:
                    pass
                print(f"  [键盘搜索] '{keyword}' 搜索完成")
                return True
            except Exception as e:
                print(f"  [键盘搜索] 尝试{attempt+1}失败: {e}")
                time.sleep(1)
        print("  [键盘搜索] 全部尝试失败")
        return False

    # ── 登录 ──
    def _login_if_needed(self, page):
        self._goto_safe(page, "https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=60000)
        time.sleep(random.uniform(2, 4))
        if '登录' in page.inner_text('body')[:200]:
            print("[!] 请扫码登录...")
            for _ in range(30):
                time.sleep(random.uniform(8, 12))
                try:
                    page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=60000)
                    time.sleep(random.uniform(2, 4))
                except:
                    pass
                try:
                    if '登录' not in page.inner_text('body')[:100]:
                        print("[OK] 登录成功")
                        break
                except:
                    pass

    # ── 浏览器启动 ──
    def _launch_browser(self):
        if self._shared_page:
            return self._shared_page, self._shared_context
        # 多路径查找Edge
        import shutil as _shutil
        edge_paths = [
            _shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        executable_path = None
        for p in edge_paths:
            if p and os.path.exists(p):
                executable_path = p
                break
        if executable_path:
            self.config.ua = self.config.ua.replace('Chrome/131.0.0.0', 'Chrome/131.0.0.0 Edg/131.0.0.0')
        # 每次启动微调 Chrome 版本号，避免固定指纹
        chrome_ver = f"Chrome/{random.randint(128,132)}.0.{random.randint(0,9999)}.{random.randint(0,999)}"
        self.config.ua = self.config.ua.replace('Chrome/131.0.0.0', chrome_ver)

        # 清理锁文件+退出状态，避免 TargetClosedError
        ud = self.config.user_data
        os.makedirs(ud, exist_ok=True)
        for name in ['SingletonLock', 'SingletonSocket', 'SingletonCookie',
                     'lockfile', 'Lockfile', 'Local State']:
            p = os.path.join(ud, name)
            try:
                if os.path.isfile(p):
                    os.remove(p)
                elif os.path.isdir(p) and name.startswith('Singleton'):
                    import shutil
                    shutil.rmtree(p, ignore_errors=True)
            except:
                pass
        # 杀掉占用此目录的Edge进程
        try:
            os.system(f'taskkill /F /IM msedge.exe /FI "USERNAME eq {os.environ.get("USERNAME","")}" 2>nul')
            time.sleep(0.5)
        except:
            pass

        # IP 轮换（如启用）
        rotator = IpRotator(self.config)
        if self.config.ip_rotate_enabled and self.config.ip_rotate_frequency == "task":
            rotator.rotate()

        self.playwright = sync_playwright().start()
        vw = random.randint(1260, 1360)
        vh = random.randint(860, 960)
        ctx_kwargs = dict(
            headless=False,
            executable_path=executable_path,
            viewport={"width": vw, "height": vh},
            user_agent=self.config.ua, locale="zh-CN",
            timezone_id="Asia/Shanghai",
            color_scheme="light",
            device_scale_factor=1,
            permissions=["geolocation"],
            geolocation={"latitude": 31.2304, "longitude": 121.4737},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=Translate,OptimizationHints,MediaRouter,DialMediaRouteProvider",
                "--no-first-run", "--no-default-browser-check",
                "--disable-background-networking", "--disable-sync",
                "--disable-default-apps", "--disable-extensions",
                "--disable-component-update", "--disable-domain-reliability",
                "--disable-client-side-phishing-detection",
                "--metrics-recording-only", "--no-pings",
                f"--window-size={vw},{vh}",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--enforce-webrtc-ip-permission-check",
                "--disable-breakpad", "--disable-crash-reporter",
                "--disable-notifications",
                "--disable-logging", "--disable-ipv6",
                "--disable-popup-blocking",
                "--disable-hang-monitor",
                "--disable-prompt-on-repost",
                "--disable-infobars",
            ])
        # 代理配置
        if self.config.ip_rotate_enabled and self.config.ip_rotate_method == "proxy" and self.config.proxy_host:
            proxy_server = f"{self.config.proxy_type}://{self.config.proxy_host}:{self.config.proxy_port}"
            ctx_kwargs["proxy"] = {"server": proxy_server}
            if self.config.proxy_username:
                ctx_kwargs["proxy"]["username"] = self.config.proxy_username
                ctx_kwargs["proxy"]["password"] = self.config.proxy_password
            print(f"  [Proxy] {proxy_server}")
        context = self.playwright.chromium.launch_persistent_context(
            self.config.user_data, **ctx_kwargs
        )
        context.add_init_script(STEALTH_JS)
        context.on('response', self._handle_search_response)
        context.route("**/search/**", self._handle_search_route)
        context.route("**/api/sns/**", self._handle_search_route)

        def block_profile_route(route):
            route.abort()
        context.route("**/user/profile/**", block_profile_route)

        pages = context.pages
        page = pages[0] if pages else context.new_page()

        cookie_file = self.config.cookie_file
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                if isinstance(cookies, list):
                    context.add_cookies(cookies)
            except:
                pass

        self._login_if_needed(page)
        self._session_warmup(page)

        try:
            context.storage_state(path=cookie_file)
        except:
            pass

        return page, context

    # ── 主入口 ──
    def run(self):
        try:
            self._setup_output_dir()
            print("=" * 60)
            print(f"  小红书采集 - {self.config.target}")
            print(f"  关键词: {self.config.keyword}")
            print(f"  输出: {self.out_dir}")
            print("=" * 60)
            self._run_impl()
        except Exception as e:
            msg = traceback.format_exc()
            print(msg)
            with open(os.path.join(self.config.output_base, 'error.log'), 'w', encoding='utf-8') as f:
                f.write(msg)
            ctypes.windll.user32.MessageBoxW(0, msg[:500], "脚本崩溃", 0)
        finally:
            if hasattr(self, 'playwright'):
                self.playwright.stop()
            print("\n全部完成!")

    def _run_impl(self):
        raise NotImplementedError
