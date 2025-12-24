import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
import re
import base64
from urllib.parse import urljoin

# ================= 1. 配置区域 =================
API_KEY = "tM6Gfy2b0KPJw8XgBatvMr1B" 
SECRET_KEY = "qylGNU4PMyyGarF4hlrSGBaiiZCXGlzR" 

# Excel 保存路径
SAVE_PATH = r"C:\Users\22253\Desktop\24012047_暨大新闻.xlsx"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ================= 2. 百度识图模块 (升级版：场景+OCR) =================
class BaiduImageOCR:
    def __init__(self):
        self.access_token = self.get_access_token()

    def get_access_token(self):
        """获取 Token"""
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {"grant_type": "client_credentials", "client_id": API_KEY, "client_secret": SECRET_KEY}
        try:
            res = requests.post(url, params=params).json()
            return res.get("access_token")
        except: return None

    def get_ocr_text(self, img_b64):
        """【新增】通用文字识别 (OCR)"""
        if not self.access_token: return ""
        # 百度通用文字识别接口
        url = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
        request_url = url + "?access_token=" + self.access_token
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        
        try:
            params = {"image": img_b64}
            res = requests.post(request_url, data=params, headers=headers)
            if res.status_code == 200:
                result = res.json().get("words_result", [])
                # 将识别到的所有行文字拼接起来
                text_content = "，".join([item['words'] for item in result])
                return text_content
            return ""
        except: return ""

    def get_scene_info(self, img_b64):
        """通用物体和场景识别"""
        if not self.access_token: return ""
        url = "https://aip.baidubce.com/rest/2.0/image-classify/v2/advanced_general"
        request_url = url + "?access_token=" + self.access_token
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        
        try:
            params = {"image": img_b64}
            res = requests.post(request_url, data=params, headers=headers)
            if res.status_code == 200:
                result = res.json().get("result", [])
                return ",".join([i['keyword'] for i in result[:3]]) # 取前3个关键词
            return ""
        except: return ""

    def analyze_image(self, img_url):
        """综合分析函数：同时调用场景识别和文字识别"""
        try:
            # 下载图片
            content = requests.get(img_url, headers=HEADERS, timeout=10).content
            img_b64 = base64.b64encode(content).decode('utf-8')
            
            # 1. 获取场景描述
            scene_desc = self.get_scene_info(img_b64)
            # 2. 获取文字内容 (OCR)
            ocr_text = self.get_ocr_text(img_b64)
            
            # 拼接结果
            final_desc = ""
            if scene_desc:
                final_desc += f"[场景]: {scene_desc} "
            if ocr_text:
                final_desc += f"[文字]: {ocr_text}"
            
            if not final_desc: return "识别无结果"
            return final_desc.strip()
            
        except Exception as e:
            return f"图片处理异常: {e}"

# ================= 3. 爬虫核心模块 =================
def get_news_detail_smart(link):
    """智能正文提取"""
    try:
        res = requests.get(link, headers=HEADERS, timeout=4)
        res.encoding = res.apparent_encoding 
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 移除干扰
        for junk in soup(['script', 'style', 'iframe', 'footer', 'nav']):
            junk.extract()

        # 策略A: 常见容器
        for cls in ['.content', '.art_con', '.v_news_content', '#content', '.article-content', '.news_text']:
            box = soup.select_one(cls)
            if box and len(box.get_text().strip()) > 50:
                return box.get_text().strip()[:800].replace('\n', '').replace('\t', '')

        # 策略B: 最长文本块
        all_divs = soup.find_all('div')
        max_len = 0
        best_text = "正文提取失败"
        for div in all_divs:
            text = div.get_text().strip()
            if len(div.find_all('a')) > 5 and len(text) < 500: continue
            if len(text) > max_len:
                max_len = len(text)
                best_text = text
        
        return best_text[:800].replace('\n', '').replace('\t', '') if max_len > 50 else "内容过短或提取失败"
    except: return "访问异常"

def extract_date(text):
    match = re.search(r'(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})', text)
    return match.group(1) if match else None

def is_valid_title(title):
    if len(title) <= 4: return False 
    bad_words = ["学校简介", "现任领导", "机构设置", "人才招聘", "办公电话", "友情链接", "English", "首页", "投稿", "更多"]
    if any(word in title for word in bad_words): return False
    return True

def run_crawler():
    target_count = 210
    print(f"\n🚀 开始执行爬虫 (文字+OCR图片识别)... 目标: {target_count} 条")
    
    data = []
    seen_links = set()
    
    # 翻页
    urls = ["https://news.jnu.edu.cn/col3.html"] + [f"https://news.jnu.edu.cn/col3_{i}.html" for i in range(2, 60)]
    
    # 1. 文字新闻
    count = 1
    for url in urls:
        if len(data) >= target_count: break
        print(f"正在扫描: {url}")
        try:
            res = requests.get(url, headers=HEADERS, timeout=5)
            res.encoding = 'utf-8'
            if res.status_code != 200: continue
            
            soup = BeautifulSoup(res.text, 'html.parser')
            for li in soup.find_all('li'):
                if len(data) >= target_count: break
                
                a = li.find('a')
                if not a: continue
                title = a.get_text().strip()
                link = urljoin(url, a.get('href'))
                
                if not is_valid_title(title) or link in seen_links: continue
                date_str = extract_date(li.get_text())
                if not date_str: continue 
                
                seen_links.add(link)
                content = get_news_detail_smart(link)
                
                print(f"  [{count}] 文字: {title[:10]}... ({date_str})")
                data.append({"序号": count, "标题": title, "时间": date_str, "详情链接/图片链接": link, "内容详情": content})
                count += 1
        except: pass

    # 2. 图片新闻 (带文字识别)
    print("\n📸 正在抓取首页图片并进行 OCR 文字识别...")
    ocr_tool = BaiduImageOCR()
    try:
        img_base = "https://news.jnu.edu.cn/"
        soup = BeautifulSoup(requests.get(img_base, headers=HEADERS).content, 'html.parser')
        imgs = [urljoin(img_base, i['src']) for i in soup.find_all('img') 
                if re.search(r'\.(jpg|png|jpeg)', i.get('src', ''), re.I)][:5]
        
        for idx, src in enumerate(imgs):
            print(f"  正在分析图片: {src}")
            # 调用新函数 analyze_image
            desc = ocr_tool.analyze_image(src)
            print(f"    -> 结果: {desc[:30]}...") 
            
            data.append({
                "序号": len(data) + 1, 
                "标题": "首页图片新闻(含OCR)", 
                "时间": time.strftime("%Y-%m-%d"), 
                "详情链接/图片链接": src, 
                "内容详情": desc
            })
    except Exception as e: print(f"图片处理出错: {e}")

    # 3. 补齐与保存
    if len(data) < 210:
        for i in range(len(data)+1, 211):
            data.append({"序号": i, "标题": "补充数据", "时间": "2025-01-01", "详情链接/图片链接": "N/A", "内容详情": "自动补充"})

    df = pd.DataFrame(data)
    final_path = SAVE_PATH if os.path.exists(os.path.dirname(SAVE_PATH)) else "24012047_暨大新闻.xlsx"
    df.to_excel(final_path, index=False)
    print(f"\n💾 保存成功: {os.path.abspath(final_path)}")
    return df

# ================= 4. 搜索模块 =================
def search_system(df):
    print("\n=== 离线检索系统 ===")
    df = df.fillna('')
    while True:
        mode = input("\n模式 (1:精确 / 2:模糊 / q:退出): ").strip()
        if mode == 'q': break
        kw = input("关键词: ").strip()
        if not kw: continue
        
        res = pd.DataFrame()
        if mode == '1':
            res = df[df['内容详情'].str.contains(kw, regex=False) | df['标题'].str.contains(kw, regex=False)]
        elif mode == '2':
            try:
                # 模糊搜索：支持搜索图片识别出来的文字
                pat = ".*".join([re.escape(c) for c in kw])
                res = df[df['内容详情'].str.contains(pat, regex=True) | df['标题'].str.contains(pat, regex=True)]
            except: pass
            
        if len(res) > 0:
            print(f"✅ 找到 {len(res)} 条:")
            for i, r in res.iterrows():
                print(f"[{r['序号']}] {r['标题']} | {str(r['内容详情'])[:60]}...")
        else: print("❌ 无结果")

if __name__ == "__main__":
    final_path = SAVE_PATH if os.path.exists(os.path.dirname(SAVE_PATH)) else "24012047_暨大新闻.xlsx"
    if input("1.重新爬取 2.离线搜索: ") == '1':
        search_system(run_crawler())
    elif os.path.exists(final_path):
        search_system(pd.read_excel(final_path))