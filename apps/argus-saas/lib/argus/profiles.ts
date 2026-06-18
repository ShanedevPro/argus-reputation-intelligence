export const ARGUS_PROFILE_IDS = [
  "generic_event_risk",
  "artist_management",
  "enterprise_pr",
] as const;

export type ArgusProfileId = (typeof ARGUS_PROFILE_IDS)[number];

export type ArgusProfile = {
  id: ArgusProfileId;
  label: string;
  description: string;
};

export const DEFAULT_ARGUS_PROFILE_ID: ArgusProfileId = "generic_event_risk";

export const ARGUS_PROFILES: Record<ArgusProfileId, ArgusProfile> = {
  generic_event_risk: {
    id: "generic_event_risk",
    label: "通用事件风险",
    description: "适用于公共事件、品牌或个人争议的通用风险研判。",
  },
  artist_management: {
    id: "artist_management",
    label: "艺人明星舆情",
    description: "面向艺人经纪、工作室和公关团队的微博舆情研判。",
  },
  enterprise_pr: {
    id: "enterprise_pr",
    label: "企业公关舆情",
    description: "面向企业公关、品牌、客服、法务和管理层的声誉风险研判。",
  },
};

export function normalizeArgusProfileId(value: unknown): ArgusProfileId {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (isArgusProfileId(normalized)) {
    return normalized;
  }

  if (["通用事件风险", "通用风险", "generic"].includes(normalized)) {
    return "generic_event_risk";
  }
  if (normalized === "genericeventrisk") {
    return "generic_event_risk";
  }
  if (
    [
      "艺人明星舆情",
      "明星艺人舆情",
      "艺人/明星舆情",
      "艺人",
      "明星",
      "artist",
      "artistmanagement",
    ].includes(normalized)
  ) {
    return "artist_management";
  }
  if (
    [
      "企业公关声誉",
      "企业公关舆情",
      "企业公关",
      "企业舆情",
      "品牌声誉",
      "enterprise",
      "enterprisepr",
    ].includes(normalized)
  ) {
    return "enterprise_pr";
  }

  return DEFAULT_ARGUS_PROFILE_ID;
}

export function getArgusProfile(id: unknown): ArgusProfile {
  return ARGUS_PROFILES[normalizeArgusProfileId(id)];
}

function isArgusProfileId(value: string): value is ArgusProfileId {
  return (ARGUS_PROFILE_IDS as readonly string[]).includes(value);
}
