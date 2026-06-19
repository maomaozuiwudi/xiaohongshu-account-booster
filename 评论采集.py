"""
小红书采集 - 评论采集模式
"""
import re, time, random, os, json, csv
from datetime import datetime
from 基础模块 import Config, BaseCrawler


class CommentsCrawler(BaseCrawler):
    def _check_verification(self, page):
        try:
            for sel in ['.captcha', '[class*="captcha"]', '[class*="slider"]',
                        '[class*="verify"]', '[class*="verification"]',
                        'iframe[src*="captcha"]']:
                if page.locator(sel).count() > 0:
                    return True
            for sel in ['[class*="modal"]', '[class*="dialog"]', '[class*="overlay"]']:
                el = page.locator(sel).first
                if el.count() > 0:
                    try:
                        text = el.inner_text()
                        for kw in ['验证', '滑动', 'security', 'captcha']:
                            if kw in text:
                                return True
                    except:
                        pass
        except:
            pass
        return False

    def _collect_comments_for_note(self, page, card_idx=0):
        for _ in range(card_idx):
            page.mouse.wheel(0, 700)
            time.sleep(random.uniform(0.3, 0.5))
        clicked = False
        for sel in ['a[href*="/explore/"]', 'section a[href]', 'div[class*="note"] a']:
            try:
                links = page.locator(sel)
                for idx in range(links.count()):
                    box = links.nth(idx).bounding_box()
                    if box and box['y'] > 80:
                        page.mouse.click(box['x'] + box['width'] * 0.85, box['y'] + box['height'] * 0.5)
                        clicked = True
                        break
                if clicked:
                    break
            except:
                continue
        if not clicked:
            return []
        time.sleep(random.uniform(3, 5))
        if self._check_verification(page):
            return None
        for _ in range(15):
            page.evaluate("""() => {
                const first = document.querySelector('.comment-inner-container, [class*="comment-item"]');
                if (first) { let p = first.parentElement; while (p) { if (p.scrollHeight > p.clientHeight) { p.scrollTop += 500; return; } p = p.parentElement; } }
                window.scrollBy(0, 300);
            }""")
            time.sleep(random.uniform(0.12, 0.18))
        cmts = page.evaluate("""
            () => {
                const results = []; const seen = new Set();
                document.querySelectorAll('.comment-inner-container, [class*="comment-item"]').forEach(el => {
                    const fullText = el.textContent.trim();
                    if (!fullText || fullText.length < 5 || seen.has(fullText)) return;
                    seen.add(fullText);
                    const getTxt = (s) => { const e = el.querySelector(s); return e ? e.textContent.trim() : ''; };
                    let author = getTxt('.author a') || getTxt('[class*="name"]');
                    let content = getTxt('span:not([class*="icon"]):not([class*="like"]):not([class*="time"])');
                    if (!content || content.length < 3) content = fullText.replace(/\\d+赞.*/, '').trim();
                    let time = getTxt('[class*="time"]') || getTxt('[class*="date"]');
                    let ip = (fullText.match(/IP[：:].{0,20}|来自.{0,10}|[粤京沪浙粤苏][^\\s]{0,5}/) || [''])[0].trim();
                    const m = fullText.match(/赞[：:\\s]*(\\d+)/);
                    results.push({author: author.slice(0,30), content: content.slice(0,500),
                                   time: time.slice(0,30), ip: ip.slice(0,20), like_count: m ? parseInt(m[1]) : 0});
                });
                return results;
            }
        """)
        return cmts

    def _parse_comment_data(self, raw_comments, note_id, note_title):
        parsed = []
        for c in raw_comments:
            ts = c.get('create_time', 0)
            time_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') if ts else ''
            parsed.append({'note_id': note_id, 'note_title': note_title,
                           'author': c.get('user_info', {}).get('nickname', ''),
                           'content': c.get('content', ''), 'time': time_str,
                           'ip': c.get('ip_location', ''), 'like_count': int(c.get('like_count', 0))})
        return parsed

    def _write_comment_csv(self, path, comment_list):
        header_map = {'note_id': '笔记ID', 'note_title': '笔记标题', 'author': '作者',
                      'content': '评论内容', 'time': '发布时间', 'ip': 'IP归属地',
                      'like_count': '点赞数'}
        fields = list(header_map.keys())
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            wr = csv.writer(f)
            wr.writerow([header_map[k] for k in fields])
            for c in comment_list:
                row = [str(c.get(f, '')).replace('\n', ' ').replace('\r', ' ') for f in fields]
                wr.writerow(row)

    def _find_note_output_dir(self, note_id):
        posts_dir = os.path.join(self.out_dir, "posts")
        if not os.path.isdir(posts_dir):
            return None
        for d in os.listdir(posts_dir):
            if note_id in d:
                return os.path.join(posts_dir, d)
        return None

    def _export_comments_csv(self, all_comments):
        if not all_comments:
            return
        merged = os.path.join(self.out_dir, "comments_all.csv")
        self._write_comment_csv(merged, all_comments)
        print(f"  全部评论: {merged} ({len(all_comments)}条)")
        by_note = {}
        for c in all_comments:
            by_note.setdefault(c['note_id'], []).append(c)
        for nid, cmts in by_note.items():
            ndir = self._find_note_output_dir(nid)
            if ndir:
                self._write_comment_csv(os.path.join(ndir, "comments.csv"), cmts)

    def _run_impl(self):
        page, context = self._launch_browser()
        try:
            all_comment_records = []
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={self.config.keyword}"
            collected = self.checkpoint.data.get("current_page", 0) if self.checkpoint.enabled else 0
            if collected:
                print(f"  [断点] 从第{collected}篇笔记恢复")
            retry = 0
            while collected < self.config.max_comment_pages:
                if self._forbidden:
                    print("  [✗] 访问被禁止(403), 停止采集")
                    break
                if self._rate_limited:
                    delay = min(2 ** self._consecutive_errors * 5, 120)
                    print(f"  [!] 被限流, 等待 {delay}s...")
                    time.sleep(delay)
                    self._rate_limited = False
                retry += 1
                self._goto_safe(page, search_url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_selector('a[href*="/explore/"]', timeout=15000)
                except:
                    pass
                time.sleep(random.uniform(2, 3))
                raw = self._collect_comments_for_note(page, retry - 1)
                if raw is None:
                    continue
                if raw:
                    for c in raw:
                        all_comment_records.append({'note_id': '', 'note_title': '',
                            'author': c.get('author', ''), 'content': c.get('content', ''),
                            'time': c.get('time', ''), 'ip': c.get('ip', ''),
                            'like_count': int(c.get('like_count', 0))})
                    collected += 1
                    print(f"  [{collected}/{self.config.max_comment_pages}] 获{len(raw)}条")
                    if self.checkpoint.enabled:
                        self.checkpoint.set_page(collected)
                        self.checkpoint.save()
            if self.comment_responses:
                api_parsed = self._parse_comment_data(self.comment_responses, '', '')
                all_comment_records.extend(api_parsed)
                print(f"  API评论补充: {len(api_parsed)}条")
            # 去重
            seen = set()
            unique = []
            for c in all_comment_records:
                key = (c.get('author',''), c.get('content',''), c.get('time',''))
                if key not in seen:
                    seen.add(key)
                    unique.append(c)
            if unique:
                print(f"  去重后{len(unique)}条 (原{len(all_comment_records)}条)")
                self._export_comments_csv(unique)
            else:
                print("  未采集到任何评论")
        finally:
            if not self._shared_page:
                page.close()
                context.close()


if __name__ == '__main__':
    cfg = Config()
    cfg.target = "评论"
    CommentsCrawler(cfg).run()
