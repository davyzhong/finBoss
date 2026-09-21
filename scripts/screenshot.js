/**
 * finBoss README 渲染截图（Playwright）
 *
 * 用途：
 *   finBoss 是 FastAPI + Next.js 财务问答 Web 应用，没有本地可执行入口。
 *   统一采用"截 GitHub README 渲染快照"方案：
 *     1. 加载 GitHub 仓库 README 渲染后的页面
 *     2. 等待 markdown 完全渲染
 *     3. 截取 article 区域（README 主体）
 *     4. 桌面 1280×800 + 移动 390×844 各一张
 *   满足 readme-craft v2.2 T18 截图自动化铁律。
 *
 * 使用方法：
 *   1. npm install
 *   2. npx playwright install chromium
 *   3. npm run screenshot
 *
 * 或通过 GitHub Action 自动跑：
 *   .github/workflows/screenshot.yml
 *
 * 输出：assets/screenshots/*.png
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'assets', 'screenshots');

// 仓库 README 渲染 URL（GitHub 自动渲染 README.md 到 <article> 元素）
const REPO_URL = 'https://github.com/davyzhong/finBoss';

// 截图配置：每张图 = { name, viewport, selector }
const SCREENSHOT_CONFIG = [
  {
    name: 'readme-desktop.png',
    viewport: { width: 1280, height: 800 },
    selector: 'article',
    description: 'finBoss README 桌面端渲染快照（1280×800）',
  },
  {
    name: 'readme-mobile.png',
    viewport: { width: 390, height: 844 }, // iPhone 14 视口
    selector: 'article',
    description: 'finBoss README 移动端渲染快照（390×844）',
  },
];

async function ensureOutputDir() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    console.log(`📂 创建目录：${OUTPUT_DIR}`);
  }
}

async function main() {
  console.log(`📸 finBoss README 截图自动化（Playwright）`);
  console.log(`📂 项目根：${PROJECT_ROOT}`);
  console.log(`🌐 加载：${REPO_URL}\n`);

  await ensureOutputDir();

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();

  let success = 0;
  let failed = 0;

  for (const config of SCREENSHOT_CONFIG) {
    const page = await context.newPage();
    try {
      console.log(`▶ ${config.name}  (${config.viewport.width}x${config.viewport.height})`);
      console.log(`  ${config.description}`);

      await page.setViewportSize(config.viewport);
      await page.goto(REPO_URL, { waitUntil: 'networkidle', timeout: 60000 });

      // 等 README 渲染完成
      await page.waitForSelector(config.selector, { timeout: 30000 });
      // 给 markdown 完全渲染 + 图片懒加载一点时间
      await page.waitForTimeout(2000);

      const outputPath = path.join(OUTPUT_DIR, config.name);

      // 截取 article 元素（README 主体）
      const article = page.locator(config.selector).first();
      await article.screenshot({ path: outputPath });

      const size = fs.statSync(outputPath).size;
      console.log(`  ✓ 写入 ${outputPath} (${(size / 1024).toFixed(1)} KB)\n`);
      success++;
    } catch (err) {
      console.error(`  ✗ 失败：${err.message}\n`);
      failed++;
    } finally {
      await page.close();
    }
  }

  await browser.close();

  console.log(`\n📊 总结：成功 ${success} / 失败 ${failed} / 总共 ${SCREENSHOT_CONFIG.length}`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('Fatal:', err);
  process.exit(1);
});