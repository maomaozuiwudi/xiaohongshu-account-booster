"""
小红书采集 - 作品模式（搜索 + 下载）
"""
import re, time, random, os, json, csv
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests as req
from 基础模块 import Config, BaseCrawler, RateLimiter


class NotesCrawler(BaseCrawler):
    def __init__(self, config):
        super().__init__(config)
        self._notes_debug_printed = False

    def parse_items(self, items):
        notes = []
        for i, item in enumerate(items):
            nid = item.get('id', '')
            nc = item.get('note_card', item)
            title = nc.get('display_title', '')
            user = nc.get('user', {})
            author = user.get('nickname', '')
            user_id = user.get('user_id', '')
            interact = nc.get('interact_info', {})

            def _parse_count(raw):
                s = str(raw).replace(',', '').replace('，', '')
                try:
                    return int(float(s))
                except:
                    return 0

            likes = _parse_count(interact.get('liked_count', '0'))
            collects = _parse_count(interact.get('collected_count', '0'))
            comments = _parse_count(interact.get('comment_count', '0'))
            cover = nc.get('cover', {})
            cover_url = cover.get('url', cover.get('url_default', ''))
            image_urls = []
            for img in nc.get('image_list', []):
                for info in img.get('info_list', []):
                    if info.get('image_scene') == 'WB_DFT':
                        u = info.get('url', '')
                        if u:
                            image_urls.append(u)
                        break

            note_type = item.get('type', nc.get('type', ''))
            video_info = nc.get('video', item.get('video', None))
            is_video = (note_type == 'video' or bool(video_info))
            video_url = ''
            if is_video and video_info:
                streams = video_info.get('media', {}).get('stream', {})
                for codec in ['h264', 'h265', 'h266']:
                    variants = streams.get(codec, [])
                    if variants:
                        video_url = variants[0].get('master_url', '')
                        if video_url:
                            break
                if not video_url:
                    video_url = video_info.get('master_url', '')

            if i < 3 and not self._notes_debug_printed:
                self._notes_debug_printed = True
                print(f"  [DEBUG笔记] 赞{likes} 藏{collects} 评{comments} {title[:30]}"
                      f" 图片{len(image_urls)}张"
                      f" {'[视频]' if is_video else ''}")

            if nid and title:
                notes.append({
                    'note_id': nid, 'title': title, 'author': author,
                    'user_id': user_id, 'likes': likes,
                    'collects': collects, 'comments': comments,
                    'cover_url': cover_url, 'image_urls': image_urls,
                    'note_url': f"https://www.xiaohongshu.com/explore/{nid}",
                    'is_video': is_video, 'video_url': video_url
                })
        return notes

    def _click_filter_opt(self, page, label, target):
        """打开筛选面板→点标签→点选项"""
        page.evaluate("""() => {
            const all = Array.from(document.querySelectorAll('*'));
            for (const el of all) {
                if ((el.textContent||'').trim() === '筛选' && el.children.length <= 2) {
                    el.click(); return;
                }
            }
        }""")
        time.sleep(1.5)
        page.evaluate("""(lb) => {
            const all = Array.from(document.querySelectorAll('*'));
            for (const el of all) {
                if ((el.textContent||'').trim().includes(lb) && el.children.length <= 2) {
                    el.click(); return;
                }
            }
        }""", label)
        time.sleep(0.5)
        type_map = {"视频": "视频笔记", "图文": "普通笔记"}
        t = type_map.get(target, target)
        pos = page.evaluate("""(t) => {
            const all = Array.from(document.querySelectorAll('*'));
            for (const el of all) {
                const tx = (el.textContent||'').trim();
                if (tx === t && el.children.length <= 1) {
                    const b = el.getBoundingClientRect();
                    if (b && b.x > 500 && b.width > 15 && b.height > 5)
                        return JSON.stringify({x: b.x + b.width/2, y: b.y + b.height/2});
                }
            }
            return '';
        }""", t)
        if pos:
            p = json.loads(pos)
            page.mouse.click(p['x'], p['y'])
        time.sleep(3)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except:
            pass

    def _search_notes(self, page):
        """让页面自己发请求翻页，我们只拦截响应"""
        cfg = self.config
        if self.checkpoint.enabled and self.checkpoint.data.get("stage") == "searched":
            last_page = self.checkpoint.data.get("current_page", 0)
            print(f"  [断点] 从第{last_page}页恢复")
        print(f"  搜索作品 (关键词: {cfg.keyword})...")
        # 键盘搜索（比直接URL导航更拟真）
        ok = self._search_via_keyboard(page, cfg.keyword)
        if not ok:
            print("  回退URL导航...")
            self._goto_safe(page, f"https://www.xiaohongshu.com/search_result?keyword={cfg.keyword}",
                           wait_until="domcontentloaded", timeout=60000)
        time.sleep(random.uniform(2, 3))

        # 逐项应用筛选
        groups = [
            ("排序依据", cfg.sort_by, "综合"),
            ("发布时间", cfg.publish_time, "不限"),
            ("搜索范围", cfg.search_scope, "不限"),
        ]
        for label, target, default in groups:
            if target != default:
                self._click_filter_opt(page, label, target)
                print(f"  筛选: {label} → {target}")
        self.captured_responses.clear()
        # 鼠标移出筛选面板
        page.mouse.move(100, 400)
        time.sleep(0.5)

        last_count = len(self.captured_responses)
        print(f"  筛选完成, 开始接收数据")
        stale = 0
        for step in range(cfg.max_pages * 3):
            if self._forbidden:
                print("  [✗] 访问被禁止(403), 停止采集")
                break
            if self._rate_limited:
                delay = min(2 ** self._consecutive_errors * 5, 120)
                print(f"  [!] 被限流, 等待 {delay}s...")
                time.sleep(delay)
                self._rate_limited = False
            self._human_scroll(page, random.randint(300, 600))
            base_wait = 0.5 + stale * 0.3
            time.sleep(random.uniform(base_wait, base_wait + 0.5))
            self._human_pause(1.0, 3.0)
            self._idle_mouse_wander(page, chance=0.3)
            self._occasional_long_read(page, step)
            if self._check_and_handle_verification(page):
                continue

            current = len(self.captured_responses)
            if current > last_count:
                last_count = current
                stale = 0
                print(f"    已收{current}批数据")
                if self.checkpoint.enabled:
                    self.checkpoint.set_page(current)
                    self.checkpoint.save()
            else:
                stale += 1

            if current >= cfg.max_pages:
                print(f"  收够{cfg.max_pages}批数据，停止")
                break
            if stale >= 6 and stale < 10:
                self._cooldown_if_stale(stale, threshold=6)
            if stale >= 10:
                print(f"  连续{stale}次无新数据，已到底")
                break
        print(f"  搜索完成: {len(self.captured_responses)}批")
        if self.checkpoint.enabled:
            self.checkpoint.set_stage("searched")
            self.checkpoint.save()

    def _download_note_media(self, note, session=None):
        """下载封面+内容图片，视频只记录链接不下载"""
        posts_dir = os.path.join(self.out_dir, "posts")
        os.makedirs(posts_dir, exist_ok=True)
        safe_title = re.sub(r'[\\/:*?"<>|]', '', note['title'])[:60]
        d = os.path.join(posts_dir, f"{safe_title}_{note['note_id']}")
        os.makedirs(d, exist_ok=True)
        headers = {"User-Agent": self.config.ua, "Referer": "https://www.xiaohongshu.com/"}
        sess = session or self._get_session()
        if not hasattr(self, '_dl_limiter'):
            self._dl_limiter = RateLimiter(max_concurrent=10)

        dl_items = []
        if note.get('cover_url'):
            dl_items.append(('cover', note['cover_url']))
        for idx, img_url in enumerate(note.get('image_urls', [])):
            dl_items.append((f"img_{idx+1}", img_url))
        # 视频下载
        if note.get('is_video') and note.get('video_url'):
            dl_items.append(('video', note['video_url']))

        def _dl(label, url, max_retries=3):
            if not url:
                return False
            if label == 'video':
                ext = '.mp4'
            else:
                em = re.search(r'\.(jpg|jpeg|png|webp)', url.split('?')[0])
                ext = '.' + em.group(1) if em else '.jpg'
            sp = os.path.join(d, f"{label}{ext}")
            if os.path.exists(sp):
                return True
            self._dl_limiter.acquire()
            try:
                for attempt in range(max_retries):
                    try:
                        r = sess.get(url, headers=headers, timeout=30)
                        if r.status_code == 200:
                            with open(sp, 'wb') as f:
                                f.write(r.content)
                            return True
                        elif r.status_code in (429, 502, 503):
                            delay = 2 ** attempt
                            print(f"    {label} HTTP {r.status_code}, 重试 {attempt+1}/{max_retries}")
                            time.sleep(delay)
                        else:
                            print(f"    {label} HTTP {r.status_code}, 放弃")
                            return False
                    except Exception as e:
                        if attempt < max_retries - 1:
                            delay = 2 ** attempt
                            print(f"    {label} 下载失败 (attempt {attempt+1}): {e}, 等{delay}s重试")
                            time.sleep(delay)
                        else:
                            print(f"    {label} 下载失败 (已重试{max_retries}次): {e}")
                            return False
            finally:
                self._dl_limiter.release()
            return False

        saved = 0
        if dl_items:
            with ThreadPoolExecutor(max_workers=15) as ex:
                fs = {ex.submit(_dl, label, url): label for label, url in dl_items}
                for f in as_completed(fs):
                    if f.result():
                        saved += 1

        is_video_note = note.get('is_video')
        video_url = note.get('video_url', '')
        info_lines = [
            f"标题:{note.get('full_title') or note['title']}",
            f"作者:{note['author']}",
            f"点赞:{note['likes']}  收藏:{note.get('collects', 0)}  评论:{note.get('comments', 0)}",
            f"类型:{'视频' if is_video_note else '图文'}",
            f"链接:{note['note_url']}",
        ]
        if is_video_note and video_url:
            info_lines.append(f"视频链接:{video_url}")
        with open(os.path.join(d, "info.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(info_lines))

        return saved, len(dl_items)

    def _find_note_output_dir(self, note_id):
        posts_dir = os.path.join(self.out_dir, "posts")
        if not os.path.isdir(posts_dir):
            return None
        for d in os.listdir(posts_dir):
            if note_id in d:
                return os.path.join(posts_dir, d)
        return None

    def _run_impl(self):
        page, context = self._launch_browser()
        try:
            self._search_notes(page)

            if not self.captured_responses:
                print("未获取到任何数据")
                return

            all_notes = {}
            for cap in self.captured_responses:
                for n in self.parse_items(cap['items']):
                    if n['note_id'] not in all_notes:
                        all_notes[n['note_id']] = n

            notes = list(all_notes.values())
            cfg = self.config
            print(f"\n搜索共获取 {len(notes)} 篇笔记")

            qualified = [n for n in notes
                         if n['likes'] >= cfg.likes_min
                         and (cfg.likes_max is None or n['likes'] <= cfg.likes_max)
                         and (n.get('cover_url') or n.get('video_url'))]
            qualified.sort(key=lambda x: x['likes'], reverse=True)
            print(f"符合条件(≥{cfg.likes_min}赞): {len(qualified)} 篇")
            for lo, hi, lbl in [(3000, 5000, '3k-5k'), (5000, 10000, '5k-1w'),
                                 (10000, 50000, '1w-5w'), (50000, 999999, '5w+')]:
                cnt = sum(1 for n in qualified if lo <= n['likes'] < hi)
                if cnt:
                    print(f"  {lbl}: {cnt}篇")

            if qualified:
                # 断点：跳过已下载的笔记
                skip_ids = set(self.checkpoint.data.get("completed_note_ids", []))
                todo = [n for n in qualified if n['note_id'] not in skip_ids]
                skipped = len(qualified) - len(todo)
                if skipped:
                    print(f"\n[断点] 跳过 {skipped} 篇已下载, 剩余 {len(todo)} 篇")
                print(f"\n下载作品 ({len(todo)}篇, 并发5篇)...")
                dl = 0
                sess = req.Session()
                with ThreadPoolExecutor(max_workers=5) as ex:
                    def _dl_one(n):
                        s, t = self._download_note_media(n, session=sess)
                        return n, s, t
                    futures = {ex.submit(_dl_one, n): n for n in todo}
                    for i, f in enumerate(as_completed(futures), 1):
                        n, s, t = f.result()
                        print(f"[{i}/{len(todo)}] {n['title'][:50]} 赞:{n['likes']} 藏:{n.get('collects',0)} 评:{n.get('comments',0)}"
                              f"{' [视频]' if n.get('is_video') else ''}  {s}/{t}个文件")
                        dl += 1
                        if self.checkpoint.enabled:
                            self.checkpoint.mark_note_done(n['note_id'])
                            self.checkpoint.save()
                sess.close()
                print(f"下载完成: {dl}/{len(todo)}")
                # CSV导出
                csv_path = os.path.join(self.out_dir, "notes.csv")
                header_map = {'note_id': '笔记ID', 'title': '标题', 'author': '作者',
                              'likes': '点赞', 'collects': '收藏', 'comments': '评论',
                              'note_url': '链接', 'is_video': '是否视频'}
                fields = list(header_map.keys())
                with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
                    wr = csv.writer(f)
                    wr.writerow([header_map[k] for k in fields])
                    for n in qualified:
                        wr.writerow([str(n.get(k, '')).replace('\n', ' ') for k in fields])
                print(f"  CSV: {csv_path}")
        finally:
            if not self._shared_page:
                page.close()
                context.close()


if __name__ == '__main__':
    cfg = Config()
    cfg.target = "作品"
    NotesCrawler(cfg).run()
