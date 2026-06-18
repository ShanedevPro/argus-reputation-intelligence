import { generateDummyPassword } from "./db/utils";

export const isProductionEnvironment = process.env.NODE_ENV === "production";
export const isDevelopmentEnvironment = process.env.NODE_ENV === "development";
export const isTestEnvironment = Boolean(
  process.env.PLAYWRIGHT_TEST_BASE_URL ||
    process.env.PLAYWRIGHT ||
    process.env.CI_PLAYWRIGHT
);

export const guestRegex = /^guest-\d+$/;

export const DUMMY_PASSWORD = generateDummyPassword();

export const suggestions = [
  "研究小米SU7最近三个月交付争议在微博上的舆论风险",
  "研究LABUBU最近三个月在微博上的热度和负面舆情",
  "研究山姆会员店最近一个月食品安全争议在微博上的扩散情况",
  "我想评估一个品牌负面事件，请先问我缺少的事件、主体和时间窗口",
];
