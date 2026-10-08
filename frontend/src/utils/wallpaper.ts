import client from '../api/client';

/** 内置壁纸（带柔和光斑纹理，磨砂模糊效果才可见） */
export const WALLPAPERS: Record<string, { label: string; bg: string }> = {
  glass: {
    label: '淡蓝紫',
    bg: [
      'radial-gradient(ellipse 600px 400px at 15% 20%, rgba(165,180,252,0.55), transparent)',
      'radial-gradient(ellipse 500px 380px at 85% 25%, rgba(186,230,253,0.55), transparent)',
      'radial-gradient(ellipse 550px 420px at 50% 90%, rgba(251,207,232,0.5), transparent)',
      'linear-gradient(135deg, #e0e7ff 0%, #f0f9ff 50%, #fdf2f8 100%)',
    ].join(', '),
  },
  ocean: {
    label: '海洋',
    bg: [
      'radial-gradient(ellipse 600px 400px at 20% 25%, rgba(125,211,252,0.5), transparent)',
      'radial-gradient(ellipse 520px 400px at 80% 70%, rgba(147,197,253,0.5), transparent)',
      'linear-gradient(135deg, #e6f4ff 0%, #bae0ff 50%, #91caff 100%)',
    ].join(', '),
  },
  aurora: {
    label: '极光',
    bg: [
      'radial-gradient(ellipse 580px 400px at 25% 20%, rgba(167,243,208,0.55), transparent)',
      'radial-gradient(ellipse 520px 420px at 80% 80%, rgba(191,219,254,0.55), transparent)',
      'linear-gradient(135deg, #f0f5ff 0%, #d6e4ff 40%, #b7ebdb 100%)',
    ].join(', '),
  },
  dusk: {
    label: '暮色',
    bg: [
      'radial-gradient(ellipse 600px 420px at 20% 25%, rgba(253,186,116,0.45), transparent)',
      'radial-gradient(ellipse 540px 400px at 80% 75%, rgba(216,180,254,0.5), transparent)',
      'linear-gradient(135deg, #fff1e6 0%, #ffd6e7 50%, #d3adf7 100%)',
    ].join(', '),
  },
  dark: {
    label: '暗夜',
    bg: [
      'radial-gradient(ellipse 620px 420px at 20% 20%, rgba(99,102,241,0.35), transparent)',
      'radial-gradient(ellipse 540px 420px at 80% 80%, rgba(56,189,248,0.25), transparent)',
      'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #312e81 100%)',
    ].join(', '),
  },
};

export const DEFAULT_WALLPAPER = 'glass';

/** 把设置值解析为 CSS background */
export function resolveWallpaper(value?: string): string {
  if (!value) return WALLPAPERS[DEFAULT_WALLPAPER].bg;
  if (WALLPAPERS[value]) return WALLPAPERS[value].bg;
  if (value.startsWith('/') || value.startsWith('http')) {
    return `url("${value}") center / cover no-repeat fixed`;
  }
  return value;
}

/** 应用到全局背景（所有页面生效） */
export function applyWallpaper(value?: string): void {
  const bg = resolveWallpaper(value);
  document.body.style.background = bg;
  document.body.style.backgroundAttachment = 'fixed';
}

/** 从后端拉取壁纸设置并应用 */
export async function loadAndApplyWallpaper(): Promise<void> {
  try {
    const res: any = await client.get('/system/login-config');
    applyWallpaper(res?.wallpaper);
  } catch {
    applyWallpaper();
  }
}
