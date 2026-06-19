"""
小红书采集 - 博主搜索模式
"""
import re, time, random, os, json, csv
from 基础模块 import Config, BaseCrawler


class BloggersCrawler(BaseCrawler):
    def _do_scroll(self, page, label):
        stale = 0
        last_count = 0
        batches_received = 0
        print(f"滚动加载{label} (最多{self.config.max_pages}页, 到底自动停)..."
              f"{'[仿生]' if self.config.bio_scroll else ''}")
        for step in range(self.config.max_pages * 5):
            if self._forbidden:
                print("  [✗] 访问被禁止(403), 停止采集")
                break
            if self._rate_limited:
                delay = min(2 ** self._consecutive_errors * 5, 120)
                print(f"  [!] 被限流, 等待 {delay}s...")
                time.sleep(delay)
                self._rate_limited = False
            if self.config.bio_scroll:
                mx = random.randint(400, 800)
                my = random.randint(300, 600)
                page.mouse.move(mx, my, steps=random.randint(3, 7))
                ticks = random.randint(2, 5)
                for _ in range(ticks):
                    dx = random.randint(-2, 2)
                    dy = random.randint(100, 300)
                    page.mouse.wheel(dx, dy)
                    page.evaluate(f"window.scrollBy({dx*5}, {dy})")
                    time.sleep(random.uniform(0.08, 0.25))
                if random.random() < 0.08:
                    dy_back = random.randint(200, 500)
                    page.mouse.wheel(0, -dy_back)
                    try:
                        page.evaluate(f"window.scrollBy(0, {-dy_back})")
                    except:
                        pass
                    time.sleep(random.uniform(0.3, 0.6))
                self._human_pause(1.5, 3.5)
            else:
                page.mouse.move(random.randint(400, 800), random.randint(300, 600), steps=random.randint(2, 4))
                try:
                    page.evaluate(f"window.scrollBy(0, {random.randint(800, 1200)})")
                except:
                    pass
                time.sleep(random.uniform(0.5, 1))
            self._human_pause(0.5, 1.5, long_chance=0.03)
            self._idle_mouse_wander(page, chance=0.3)
            self._occasional_long_read(page, step)
            current = len(self.captured_responses)
            if current > last_count:
                last_count = current
                stale = 0
                batches_received += 1
                if self.checkpoint.enabled:
                    self.checkpoint.set_page(batches_received)
                    self.checkpoint.save()
            else:
                stale += 1
            if step % 10 == 0:
                print(f"  滚动{step}... 已拦截{current}批 已收{batches_received}页 [无新数据{stale}次]")
            if batches_received >= self.config.max_pages:
                print("  已达最大页数限制")
                break
            if stale >= 8 and stale < 20:
                self._cooldown_if_stale(stale, threshold=8)
            if stale >= 20:
                print("  连续20次无新数据，已到底")
                break

    def _click_user_tab(self, page):
        def has_fans():
            return '粉丝' in page.inner_text('body')
        print("  点击'用户'tab...")
        try:
            loc = page.locator('text="用户"')
            count = loc.count()
            for i in range(count):
                el = loc.nth(i)
                box = el.bounding_box()
                if not box or box['y'] < 50 or box['y'] > 400:
                    continue
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                page.mouse.click(x, y)
                time.sleep(random.uniform(0.5, 1))
                if has_fans():
                    print("  [OK] 点击'用户'tab成功!")
                    return True
                break
        except Exception as e:
            print(f"  点击失败: {str(e)[:60]}")
        for sel in ['text=用户', '[class*=tab]:has-text("用户")']:
            try:
                el = page.locator(sel).first
                box = el.bounding_box()
                if box and box['y'] > 50 and box['y'] < 400:
                    page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                    time.sleep(random.uniform(0.5, 1))
                    if has_fans():
                        print("  [OK] 坐标点击'用户'tab成功!")
                        return True
            except:
                pass
        return False

    def _scrape_users_from_dom(self, page):
        return page.evaluate("""
            () => {
                const users = []; const seen = new Set(); const debugLines = [];
                function parseFansCount(text) {
                    if (!text) return 0;
                    let m = text.match(/([\\d,.]+)\\s*[・·]?\\s*(万|w)?\\s*[・·]?\\s*粉丝/);
                    if (m) { const num = parseFloat(m[1].replace(/,/g,'')); return m[2]?Math.round(num*10000):Math.round(num); }
                    m = text.match(/粉丝\\s*[・·]?\\s*([\\d,.]+)\\s*(万|w)?/);
                    if (m) { const num = parseFloat(m[1].replace(/,/g,'')); return m[2]?Math.round(num*10000):Math.round(num); }
                    return 0;
                }
                function parseNoteCount(text) {
                    if (!text) return 0;
                    let m = text.match(/([\\d,.]+)\\s*[・·]?\\s*(万|w)?\\s*[・·]?\\s*笔记/);
                    if (m) { const num = parseFloat(m[1].replace(/,/g,'')); return m[2]?Math.round(num*10000):Math.round(num); }
                    m = text.match(/笔记\\s*[・·]?\\s*([\\d,.]+)\\s*(万|w)?/);
                    if (m) { const num = parseFloat(m[1].replace(/,/g,'')); return m[2]?Math.round(num*10000):Math.round(num); }
                    return 0;
                }
                function isFooterOrHeader(el) {
                    const text = el.textContent||'';
                    if (/ICP|营业执照|公网安备|许可证|备案号|医疗器械|互联网药品/.test(text)) return true;
                    const tag = el.tagName.toLowerCase();
                    if(tag==='header'||tag==='footer'||tag==='nav') return true;
                    const cls = (el.className||'').toString().toLowerCase();
                    if(/footer|header|nav-bar|top-bar|sidebar/.test(cls)) return true;
                    return false;
                }
                const allLinks = Array.from(document.querySelectorAll('a[href*="/user/profile/"]'));
                const valid = allLinks.filter(l=>!isFooterOrHeader(l)&&!isFooterOrHeader(l.parentElement)&&!isFooterOrHeader(l.parentElement?.parentElement));
                if(valid.length===0) return {users:[],debug:'无有效链接'};
                for(const link of valid) {
                    const href=link.getAttribute('href');
                    const m=href.match(/profile\\/([a-zA-Z0-9]+)/);
                    const uid=m?m[1]:'';
                    if(!uid||seen.has(uid)) continue;
                    seen.add(uid);
                    let card=link;
                    for(let i=0;i<8;i++){card=card.parentElement;if(!card||isFooterOrHeader(card))break;const t=card.textContent||'';if(t.includes('粉丝')&&t.length>20&&t.length<500)break;}
                    if(!card||isFooterOrHeader(card)) continue;
                    const cardText=card.textContent||'';
                    let nickname='';
                    const els=link.querySelectorAll('span,div,p');
                    for(const el of els){const t=el.textContent.trim();if(t.length>=1&&t.length<=30&&!/(粉丝|笔记|获赞|赞与|关注|更新|天前|小时前|直播)/.test(t)){if(t!==link.textContent.trim()){nickname=t;break;}}}
                    if(!nickname){const raw=link.textContent.trim();nickname=raw.replace(/\\d+天前.*|\\d+小时前.*|\\d+分钟前.*/,'').trim().substring(0,30);}
                    if(!nickname||nickname==='我'||nickname==='直播'||nickname.length===1||/^\\d+$/.test(nickname)) continue;
                    function extractStat(card,label,parser){
                        const all=Array.from(card.querySelectorAll('*')).reverse();let best=0;
                        for(const el of all){
                            const t=(el.textContent||'').trim();
                            if(!t.includes(label)||t.length>100) continue;
                            const v=parser(t);
                            if(v>0&&t.length<30) return v;
                            if(v>0&&v>best) best=v;
                            for(const dir of ['previousElementSibling','nextElementSibling']){
                                const sib=el[dir];
                                if(sib){const st=sib.textContent.trim();if(st.length>0&&st.length<20){const v2=parser(st+label);if(v2>0)return v2;const v2b=parser(label+st);if(v2b>0)return v2b;}}
                            }
                        }
                        if(best>0) return best;
                        return parser(card.textContent.trim());
                    }
                    let fc=extractStat(card,'粉丝',parseFansCount);
                    if(fc>100000000||fc===0) fc=extractStat(card,'笔记',parseNoteCount);
                    let nc=extractStat(card,'笔记',parseNoteCount);
                    if(seen.size<=5&&debugLines.length<5) debugLines.push('[CARD'+seen.size+'] uid='+uid.substring(0,12)+' name='+nickname+' fc='+fc+' nc='+nc);
                    users.push({user_id:uid,nickname:nickname,follower_count:fc,note_count:nc,desc:'',avatar:'',profile_url:'https://www.xiaohongshu.com/user/profile/'+uid});
                }
                if(users.length===0){const body=document.body.innerText;const fi=body.indexOf('粉丝');return{users:[],debug:'body含粉丝:'+fi+' 前后文:'+body.substring(Math.max(0,fi-80),fi+120)};}
                return {users:users,debug:debugLines.join('|')};
            }
        """)

    def parse_users(self, items):
        users = []
        for item in items:
            uid = item.get('id', '')
            nickname = item.get('nickname', item.get('name', item.get('nick_name', '')))
            fc_raw = '0'
            for key in ['follower_count', 'fans_count', 'fans', 'followers', 'follow_count']:
                if key in item: fc_raw = item[key]; break
            if fc_raw == '0':
                for nested in ['user_info', 'basic_info', 'interact_info', 'stats']:
                    d = item.get(nested, {})
                    if d:
                        for key in ['follower_count', 'fans_count', 'fans', 'followers']:
                            if key in d: fc_raw = d[key]; break
                        if fc_raw != '0': break
            fc = int(str(fc_raw)) if str(fc_raw).isdigit() else 0
            nc_raw = '0'
            for key in ['note_count', 'notes_count', 'notes', 'note_total']:
                if key in item: nc_raw = item[key]; break
            nc = int(str(nc_raw)) if str(nc_raw).isdigit() else 0
            desc = item.get('desc', item.get('description', ''))
            avatar = item.get('avatar', '')
            if uid and nickname:
                users.append({'user_id': uid, 'nickname': nickname, 'follower_count': fc,
                              'note_count': nc, 'desc': desc, 'avatar': avatar,
                              'profile_url': f"https://www.xiaohongshu.com/user/profile/{uid}"})
        return users

    def _merge_all_users(self, all_captured):
        all_users = {}
        for cap in all_captured:
            items = cap['items']
            url = cap.get('url', '')
            if url.startswith('dom://'):
                for u in items:
                    uid = u.get('user_id', '')
                    if uid and uid not in all_users:
                        all_users[uid] = u
            else:
                for u in self.parse_users(items):
                    uid = u['user_id']
                    if uid not in all_users:
                        all_users[uid] = u
        return list(all_users.values())

    def _run_impl(self):
        page, context = self._launch_browser()
        try:
            kw = self.config.keyword
            print(f"搜索博主 (关键词: {kw})...")
            ok = self._search_via_keyboard(page, kw)
            if not ok:
                print("  回退URL导航...")
                self._goto_safe(page, f"https://www.xiaohongshu.com/search_result?keyword={kw}",
                              wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(2, 4))
            wd = page.evaluate("navigator.webdriver")
            pl = page.evaluate("navigator.plugins.length")
            cr = page.evaluate("!!(window.chrome && window.chrome.runtime && window.chrome.runtime.connect)")
            print(f"  [验证] webdriver={wd!r} {'[OK]' if not wd else '[X]'} plugins={pl} {'[OK]' if pl>0 else '[X]'} chrome.runtime={'[OK]' if cr else '[X]'}")
            print("切换到用户tab...")
            self._click_user_tab(page)
            self._do_scroll(page, "(用户)")
            dom_result = self._scrape_users_from_dom(page)
            if dom_result.get('debug'):
                print(f"  DOM调试: {dom_result['debug'][:300]}")
            dom_users = dom_result.get('users', [])
            if dom_users:
                print(f"  DOM抓取到 {len(dom_users)} 个用户 (前3个):")
                for u in dom_users[:3]:
                    print(f"    {u['nickname']} | 粉丝:{u['follower_count']} | 笔记:{u['note_count']}")
                self.captured_responses.append({'page': 0, 'items': dom_users, 'url': 'dom://scraped'})
            else:
                body = page.inner_text('body')
                idx = body.find('粉丝')
                if idx >= 0:
                    print(f"  body中'粉丝'前后文: ...{body[max(0,idx-80):idx+80]}...")
                else:
                    print("  [!] 页面无'粉丝'关键词")
            users = self._merge_all_users(self.captured_responses)
            users.sort(key=lambda x: x['follower_count'], reverse=True)
            print(f"\n搜索共获取 {len(users)} 个用户")
            if users:
                zero_fans = [u for u in users if u['follower_count'] == 0]
                if zero_fans and len(zero_fans) == len(users):
                    print("  [!] 所有用户粉丝数都是0！")
                print(f"\n全部用户 (按粉丝降序, 前10):")
                for i, u in enumerate(users[:10]):
                    print(f"  {i+1}. {u['nickname']} | 粉丝:{u['follower_count']} | 笔记:{u['note_count']}")
                if len(users) > 10:
                    print(f"  ... 共{len(users)}人")
            qualified = [u for u in users
                         if u['follower_count'] >= self.config.fans_min
                         and (self.config.fans_max is None or u['follower_count'] <= self.config.fans_max)]
            print(f"\n符合条件(≥{self.config.fans_min}粉丝): {len(qualified)} 人")
            if qualified:
                for lo, hi, lbl in [(1000,5000,'1k-5k'),(5000,10000,'5k-1w'),(10000,50000,'1w-5w'),
                                     (50000,100000,'5w-10w'),(100000,99999999,'10w+')]:
                    cnt = sum(1 for u in qualified if lo <= u['follower_count'] < hi)
                    if cnt:
                        print(f"  {lbl}: {cnt}人")
            cn_fields = ['用户ID', '昵称', '粉丝数', '笔记数', '简介', '头像', '主页']
            def write_csv(path, user_list):
                with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                    wr = csv.writer(f)
                    wr.writerow(cn_fields)
                    for u in user_list:
                        wr.writerow([str(u.get('user_id','')), str(u.get('nickname','')),
                               str(u.get('follower_count',0)), str(u.get('note_count',0)),
                               str(u.get('desc','')), str(u.get('avatar','')),
                               str(u.get('profile_url',''))])
            if users:
                write_csv(os.path.join(self.out_dir, "bloggers_all.csv"), users)
                print(f"全部用户已保存: bloggers_all.csv ({len(users)}人)")
            if qualified:
                write_csv(os.path.join(self.out_dir, "bloggers.csv"), qualified)
                print(f"筛选结果已保存: bloggers.csv ({len(qualified)}人)")
            elif not users:
                print("未获取到任何用户数据")
        finally:
            if not self._shared_page:
                page.close()
                context.close()


if __name__ == '__main__':
    cfg = Config()
    cfg.target = "博主"
    BloggersCrawler(cfg).run()
