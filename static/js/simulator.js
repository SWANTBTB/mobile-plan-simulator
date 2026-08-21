const form = document.getElementById("simulator-form");
const MAX_LINES = 10;
const LINE_TAB_DENSE_THRESHOLD = 5;
const LINE_TAB_MAX_COLUMNS = 5;
const DEFAULT_CARRIER = "softbank";

const DEFAULT_THEME = { border: "border-slate-300", bg: "bg-slate-50" };

function readSimulatorConfig() {
  const node = document.getElementById("simulator-config");
  if (!node) return {};
  try {
    return JSON.parse(node.textContent);
  } catch (error) {
    console.error("simulator-config の解析に失敗しました", error);
    return {};
  }
}

const SIMULATOR_CONFIG = readSimulatorConfig();
const EXCLUSIVE_DISCOUNTS = SIMULATOR_CONFIG.exclusive_discounts || {};
const HOME_SET_GROUPS = SIMULATOR_CONFIG.home_set_groups || {};
const CARRIER_UI = SIMULATOR_CONFIG.carrier_ui || {};
const HOME_SET_DISCOUNT_GROUPS = SIMULATOR_CONFIG.home_set_discount_groups || {};
const FAMILY_DISCOUNT_IDS = SIMULATOR_CONFIG.family_discount_ids || {};
const FAMILY_DISCOUNT_PRIMARY_BLOCKED = SIMULATOR_CONFIG.family_discount_primary_blocked || {};
const TENURE_AUTO_DISCOUNTS = SIMULATOR_CONFIG.tenure_auto_discounts || {
  docomo: { discount_id: "long_term", min_tenure_years: 10 },
};
const MANUAL_OPT_IN_DISCOUNT_IDS = new Set(SIMULATOR_CONFIG.manual_opt_in_discount_ids || []);
const CARRIERS_BY_ID = Object.fromEntries(
  (SIMULATOR_CONFIG.carriers || []).map((carrier) => [carrier.id, carrier])
);

const ACCOUNT_UI_FIELDS = {
  tenure_years: ["tenure_years"],
  home_set_softbank: ["home_set_softbank"],
  home_set_au: ["home_set_au"],
  home_set_docomo: ["home_set_docomo"],
  home_set_docomo_denki: ["home_set_docomo_denki"],
};

const LINE_UI_FIELDS = {
  qr_paypay: ["qr_paypay"],
  paypay_card_tier: ["paypay_card_tier"],
  paypay_gold_linked: ["paypay_gold_linked"],
  qr_dbarai: ["qr_dbarai"],
  dcard_tier: ["dcard_tier"],
  docomo_bill_dcard: ["docomo_bill_dcard"],
  qr_aupay: ["qr_aupay"],
  aupay_gold: ["aupay_gold"],
  au_bill_payment_mode: ["au_bill_payment_mode"],
  au_pay_card_bank_is_jibun: ["au_pay_card_bank_is_jibun"],
  au_jibun_bank_balance: ["au_jibun_bank_balance"],
  au_pay_card_bill: ["au_pay_card_bill"],
  au_jibun_bank: ["au_jibun_bank"],
};

function formatYen(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "---円";
  return `${amount.toLocaleString("ja-JP")}円`;
}

function getLineCarrier(lineIndex) {
  const checked = form.querySelector(`input[name="${linePrefix(lineIndex)}[carrier]"]:checked`);
  return checked?.value || DEFAULT_CARRIER;
}

function getUsedCarriers() {
  return [...new Set(getLineIndices().map(getLineCarrier))];
}

function accountFieldVisible(field) {
  return getUsedCarriers().some((carrierId) => CARRIER_UI[carrierId]?.[field]);
}

function getLineIndices() {
  return [...form.querySelectorAll("[data-line-card]")]
    .map((node) => Number(node.dataset.lineCard))
    .sort((a, b) => a - b);
}

function getActiveLineIndex() {
  const input = document.getElementById("active-line-input");
  return input ? Number(input.value) || 0 : 0;
}

function setActiveLineIndex(index) {
  const input = document.getElementById("active-line-input");
  if (input) input.value = String(index);
}

function lineLabel(index) {
  return index === 0 ? "主回線" : `${index + 1}回線目`;
}

function lineTabColumnCount(count = getLineIndices().length) {
  if (count <= 0) return 1;
  return count > LINE_TAB_DENSE_THRESHOLD ? LINE_TAB_MAX_COLUMNS : count;
}

function isLineTabsDense(count = getLineIndices().length) {
  return count > LINE_TAB_DENSE_THRESHOLD;
}

function lineTabLabel(index) {
  if (!isLineTabsDense()) return lineLabel(index);
  return index === 0 ? "主回線" : String(index + 1);
}

function lineTabTitle(index, carrierName) {
  return `${lineLabel(index)} · ${carrierName}`;
}

function linePrefix(index) {
  return `lines[${index}]`;
}

function syncAccountFieldVisibility() {
  document.querySelectorAll("[data-ui-field]").forEach((element) => {
    const field = element.dataset.uiField;
    if (field in ACCOUNT_UI_FIELDS) {
      element.classList.toggle("hidden", !accountFieldVisible(field));
    }
  });
  document.querySelectorAll("[data-ui-section]").forEach((element) => {
    if (element.dataset.uiSection === "home_set") {
      element.classList.toggle("hidden", !accountFieldVisible("home_set_section"));
    }
  });
}

function syncLineCardUiVisibility(lineIndex) {
  const ui = CARRIER_UI[getLineCarrier(lineIndex)] || {};
  const card = document.querySelector(`[data-line-card="${lineIndex}"]`);
  if (!card) return;

  card.querySelectorAll("[data-ui-field]").forEach((element) => {
    const field = element.dataset.uiField;
    if (field in LINE_UI_FIELDS) {
      element.classList.toggle("hidden", !ui[field]);
    }
  });
  card.querySelectorAll("[data-ui-section]").forEach((element) => {
    if (element.dataset.uiSection === "qr") {
      element.classList.toggle("hidden", !ui.qr_section);
    }
    if (element.dataset.uiSection === "paypay_card") {
      element.classList.toggle("hidden", !ui.paypay_card_section);
    }
  });
}

function syncAllUiVisibility() {
  syncAccountFieldVisibility();
  getLineIndices().forEach(syncLineCardUiVisibility);
}

function syncLineDataUsageInputs() {
  getLineIndices().forEach((index) => {
    const prefix = linePrefix(index);
    const input = form.querySelector(`[name="${prefix}[data_usage]"]`);
    const unlimited = form.querySelector(`[name="${prefix}[data_unlimited]"]`);
    if (input && unlimited) input.disabled = unlimited.checked;
  });
}

function pruneHiddenParams(params) {
  Object.entries(ACCOUNT_UI_FIELDS).forEach(([field, names]) => {
    if (accountFieldVisible(field)) return;
    names.forEach((name) => params.delete(name));
  });
  getLineIndices().forEach((index) => {
    const prefix = linePrefix(index);
    const ui = CARRIER_UI[getLineCarrier(index)] || {};
    Object.entries(LINE_UI_FIELDS).forEach(([field, names]) => {
      if (ui[field]) return;
      names.forEach((name) => params.delete(`${prefix}[${name}]`));
    });
  });
}

function buildParams() {
  const params = new URLSearchParams(new FormData(form));
  form.querySelectorAll('input[type="checkbox"]:disabled:checked').forEach((input) => {
    params.append(input.name, input.value);
  });

  getLineIndices().forEach((index) => {
    const prefix = linePrefix(index);
    const unlimited = form.querySelector(`[name="${prefix}[data_unlimited]"]`);
    if (unlimited?.checked) {
      params.set(`${prefix}[data_usage]`, "unlimited");
    }
    params.delete(`${prefix}[data_unlimited]`);
  });

  params.set("active_line", String(getActiveLineIndex()));
  pruneHiddenParams(params);
  return params;
}

function showError(message) {
  const banner = document.getElementById("price-error");
  if (!banner) return;
  banner.textContent = message;
  banner.classList.remove("hidden");
}

function clearError() {
  const banner = document.getElementById("price-error");
  if (banner) banner.classList.add("hidden");
}

function markDiscountUserTouched(input) {
  if (input) input.dataset.userTouched = "true";
}

function helpTipButton(text, label) {
  const safe = String(text).replace(/"/g, "&quot;");
  if (label) {
    return `<button type="button" data-tip="${safe}" class="shrink-0 rounded text-xs font-medium text-blue-600 transition hover:text-blue-800 hover:underline">${label} ›</button>`;
  }
  return `<button type="button" data-tip="${safe}" aria-label="適用される条件" class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-slate-300 text-[11px] font-bold leading-none text-slate-500">?</button>`;
}

function readCheckedDiscounts(lineIndex) {
  return new Set(
    [...form.querySelectorAll(`[name="${linePrefix(lineIndex)}[discounts]"]:checked`)].map(
      (input) => input.value
    )
  );
}

function readManualPlanId(lineIndex) {
  return form.querySelector(`[name="${linePrefix(lineIndex)}[plan]"]:checked`)?.value || null;
}

function getCarrierLineIndex(lineIndex) {
  const carrierId = getLineCarrier(lineIndex);
  let count = 0;
  for (const index of getLineIndices()) {
    if (index >= lineIndex) break;
    if (getLineCarrier(index) === carrierId) count += 1;
  }
  return count;
}

function isMainLineBlockedDiscount(carrierId, lineIndex, discountId) {
  return (
    getCarrierLineIndex(lineIndex) === 0 &&
    (FAMILY_DISCOUNT_PRIMARY_BLOCKED[carrierId] || []).includes(discountId)
  );
}

function isFamilyDiscountBlockedForResult(result, discountId) {
  const carrierLineIndex = result?.carrier_line_index ?? getCarrierLineIndex(result.line_index);
  if (carrierLineIndex !== 0) return false;
  return (FAMILY_DISCOUNT_PRIMARY_BLOCKED[result.carrier_id] || []).includes(discountId);
}

function renderAdvancedDetails(scope, hint, bodyHtml) {
  return `
    <details class="advanced-details mt-4" data-advanced-details="${scope}">
      <summary class="advanced-details__summary">
        <span class="advanced-details__title">詳細条件（任意）</span>
        <span class="advanced-details__hint">${hint}</span>
      </summary>
      <div class="advanced-details__body mt-3">${bodyHtml}</div>
    </details>`;
}

function renderCarrierRadios(lineIndex, selectedCarrierId) {
  const prefix = linePrefix(lineIndex);
  const buttons = (SIMULATOR_CONFIG.carriers || [])
    .map(
      (carrier) => `
        <label class="cursor-pointer">
          <input type="radio" name="${prefix}[carrier]" value="${carrier.id}"${
            carrier.id === selectedCarrierId ? " checked" : ""
          } class="peer sr-only" />
          <span class="border border-slate-300 bg-white font-medium text-slate-700 transition hover:border-slate-400 peer-checked:border-blue-600 peer-checked:bg-blue-600 peer-checked:font-semibold peer-checked:text-white">
            ${carrier.name}
          </span>
        </label>`
    )
    .join("");
  return `<div class="carrier-grid grid grid-cols-3 gap-1.5">${buttons}</div>`;
}

function renderLinePayPayCardSection(lineIndex, ui, prefix, carrierName) {
  const fieldClass =
    "h-11 w-full max-w-full rounded-lg border border-slate-300 bg-white px-3 text-[14px] text-slate-800";
  const labelClass = "mb-1.5 block text-[14px] font-semibold text-slate-600";
  const hiddenIf = (field) => (ui[field] ? "" : " hidden");

  return `
    <div class="mt-4 space-y-2${hiddenIf("paypay_card_section")}" data-ui-section="paypay_card">
      <p class="text-[14px] font-semibold text-slate-600">PayPayカード（${carrierName}）</p>
      <select name="${prefix}[paypay_card_tier]" class="${fieldClass} text-[13px]${hiddenIf("paypay_card_tier")}" data-ui-field="paypay_card_tier">
        <option value="">未利用</option>
        <option value="standard">ノーマル（330円/月割引）</option>
        <option value="gold">ゴールド（550円/月割引）</option>
      </select>
      <label class="mt-2 flex items-center gap-1.5 text-[12px] text-slate-600${hiddenIf("paypay_gold_linked")}" data-ui-field="paypay_gold_linked">
        <input type="checkbox" name="${prefix}[paypay_gold_linked]" value="1" class="rounded border-slate-300 text-blue-600" />
        PayPayカード ゴールドをPayPayアプリに連携済み
      </label>
    </div>`;
}

function renderLineQrSection(lineIndex, ui, prefix) {
  const fieldClass =
    "h-11 w-full max-w-full rounded-lg border border-slate-300 bg-white px-3 text-[14px] text-slate-800 placeholder:text-slate-400";
  const labelClass = "mb-1.5 block text-[14px] font-semibold text-slate-600";
  const subLabelClass = "mt-2 flex items-center gap-1.5 text-[12px] text-slate-600";

  const hiddenIf = (field) => (ui[field] ? "" : " hidden");

  return `
    <div class="mt-4 space-y-3${hiddenIf("qr_section")}" data-ui-section="qr">
      <p class="text-[14px] font-semibold text-slate-600">QR決済（この回線）</p>
      <div class="grid grid-cols-1 gap-4">
        <div class="${hiddenIf("qr_paypay").trim()}" data-ui-field="qr_paypay">
          <label class="${labelClass}">PayPay</label>
          <div class="input-with-unit">
            <input type="number" name="${prefix}[qr_paypay]" min="0" max="1000000" step="1000" placeholder="30000" class="${fieldClass}" />
            <span class="input-unit">円</span>
          </div>
        </div>
        <div class="${hiddenIf("qr_dbarai").trim()}" data-ui-field="qr_dbarai">
          <label class="${labelClass}">d払い</label>
          <div class="input-with-unit">
            <input type="number" name="${prefix}[qr_dbarai]" min="0" max="1000000" step="1000" placeholder="30000" class="${fieldClass}" />
            <span class="input-unit">円</span>
          </div>
          <select name="${prefix}[dcard_tier]" class="${fieldClass} mt-2 text-[13px]${hiddenIf("dcard_tier")}" data-ui-field="dcard_tier">
            <option value="standard">dカード一般</option>
            <option value="gold">GOLD</option>
            <option value="platinum">PLATINUM</option>
          </select>
          <label class="${subLabelClass}${hiddenIf("docomo_bill_dcard")}" data-ui-field="docomo_bill_dcard">
            <input type="checkbox" name="${prefix}[docomo_bill_dcard]" value="1" class="rounded border-slate-300 text-blue-600" />
            通信料をdカードで支払い
          </label>
        </div>
        <div class="${hiddenIf("qr_aupay").trim()}" data-ui-field="qr_aupay">
          <label class="${labelClass}">au PAY</label>
          <div class="input-with-unit">
            <input type="number" name="${prefix}[qr_aupay]" min="0" max="1000000" step="1000" placeholder="30000" class="${fieldClass}" />
            <span class="input-unit">円</span>
          </div>
          <label class="${subLabelClass}${hiddenIf("aupay_gold")}" data-ui-field="aupay_gold">
            <input type="checkbox" name="${prefix}[aupay_gold]" value="1" class="rounded border-slate-300 text-blue-600" />
            ゴールド
          </label>
          <select name="${prefix}[au_bill_payment_mode]" class="${fieldClass} mt-2 text-[13px]${hiddenIf("au_bill_payment_mode")}" data-ui-field="au_bill_payment_mode">
            <option value="other">通信料支払特典：該当なし</option>
            <option value="au_pay_card">au PAYカードで通信料支払い</option>
            <option value="au_jibun_bank_direct_debit">auじぶん銀行口座振替</option>
          </select>
          <label class="${subLabelClass}${hiddenIf("au_pay_card_bank_is_jibun")}" data-ui-field="au_pay_card_bank_is_jibun">
            <input type="checkbox" name="${prefix}[au_pay_card_bank_is_jibun]" value="1" class="rounded border-slate-300 text-blue-600" />
            au PAYカードの引落口座がauじぶん銀行
          </label>
          <div class="${hiddenIf("au_jibun_bank_balance").trim()}" data-ui-field="au_jibun_bank_balance">
            <label class="${labelClass} mt-2">auじぶん銀行 普通預金残高</label>
            <div class="input-with-unit">
              <input type="number" name="${prefix}[au_jibun_bank_balance]" min="0" max="10000000" step="10000" placeholder="500000" class="${fieldClass}" />
              <span class="input-unit">円</span>
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

function renderLineTabs() {
  const active = getActiveLineIndex();
  const indices = getLineIndices();
  const dense = isLineTabsDense(indices.length);
  const html = indices
    .map((index) => {
      const carrierName = CARRIERS_BY_ID[getLineCarrier(index)]?.name || "";
      const activeClass = active === index ? "line-tab-btn--active" : "line-tab-btn--idle";
      return `<button type="button" data-line-tab="${index}" title="${lineTabTitle(index, carrierName)}" class="line-tab-btn ${activeClass}"><span class="line-tab-btn__label">${lineTabLabel(index)}</span><span class="line-tab-btn__carrier">${carrierName}</span></button>`;
    })
    .join("");
  const tabs = document.getElementById("line-tabs");
  if (tabs) {
    tabs.classList.toggle("line-tabs--dense", dense);
    tabs.style.setProperty("--line-tab-columns", lineTabColumnCount(indices.length));
    tabs.innerHTML = html;
  }
}

function showLinePanel(lineIndex) {
  document.querySelectorAll("[data-line-card]").forEach((card) => {
    card.classList.toggle("hidden", Number(card.dataset.lineCard) !== lineIndex);
  });
  document.querySelectorAll("[data-line-panel]").forEach((panel) => {
    panel.classList.toggle("hidden", Number(panel.dataset.linePanel) !== lineIndex);
  });
  setActiveLineIndex(lineIndex);
  renderLineTabs();
}

function renderPlanComparisonNotes(carrier) {
  const notes = carrier?.plan_comparison_notes;
  if (!notes) return "";
  const rows = (notes.rows || [])
    .map((row) => `<p>${row.label}：${row.text}</p>`)
    .join("");
  return `
    <div class="plan-comparison-notes">
      <p class="plan-comparison-notes__title">※ ${notes.title}</p>
      ${rows}
    </div>`;
}

function renderLineCampaignPanel(carrier, lineIndex, result) {
  let panel = document.querySelector(`[data-line-panel="${lineIndex}"]`);
  const container = document.getElementById("campaign-panels");
  if (!container || !carrier) return;

  const prefix = linePrefix(lineIndex);
  const carrierId = carrier.id;
  const checkedDiscounts = readCheckedDiscounts(lineIndex);
  const manualPlanId = readManualPlanId(lineIndex);
  const selectedPlanId = result?.plan?.id || manualPlanId;
  const planManual = Boolean(result?.plan_manual || (manualPlanId && manualPlanId === selectedPlanId));
  const eligibility = result?.discount_eligibility || {};
  const amounts = result?.resolved_discount_amounts || {};

  const plansHtml = (carrier.plans || [])
    .map((plan) => {
      const isSelected = selectedPlanId === plan.id;
      const isManual = isSelected && planManual;
      return `
        <label data-plan-row="${lineIndex}:${plan.id}" data-plan-line="${lineIndex}" data-plan-id="${plan.id}"
          class="flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-3 ${isSelected ? "border-blue-200 bg-blue-50" : "border-slate-200 bg-white"}">
          <input type="radio" name="${prefix}[plan]" value="${plan.id}"${isManual ? " checked" : ""} class="peer sr-only" />
          <span data-plan-marker class="h-2 w-2 shrink-0 rounded-full ${isSelected ? "bg-blue-600" : "bg-slate-300"}"></span>
          <div class="min-w-0 flex-1">
            <p class="truncate text-[15px] font-medium text-slate-800" data-tip="${plan.name}">${plan.name}</p>
            ${plan.data_label ? `<p class="text-[12px] text-slate-500">${plan.data_label}</p>` : ""}
          </div>
          <span data-plan-auto-badge class="shrink-0 rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold text-blue-700${!isSelected || isManual ? " hidden" : ""}">自動</span>
          <span data-plan-manual-badge class="shrink-0 rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] font-bold text-white${!isManual ? " hidden" : ""}">選択中</span>
          <span data-plan-short-badge class="hidden shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">容量不足</span>
          <span class="shrink-0 text-right">
            <span class="block text-[16px] font-bold text-slate-900">${formatYen(plan.base_price)}</span>
            <span data-plan-effective class="hidden text-[10px] font-medium text-emerald-700"></span>
          </span>
        </label>`;
    })
    .join("");

  const discountsHtml = (carrier.discounts || []).length
    ? (carrier.discounts || [])
        .map((discount) => {
          const mainBlocked = isMainLineBlockedDiscount(carrierId, lineIndex, discount.id);
          const eligible = !mainBlocked && eligibility[discount.id] !== false;
          const groupId = HOME_SET_DISCOUNT_GROUPS[`${carrierId}:${discount.id}`];
          const amount = amounts[discount.id] ?? discount.amount;
          return `
            <div data-discount-row="${lineIndex}:${discount.id}"${groupId ? ` data-home-set-group="${groupId}"` : ""}
              class="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-3${eligible ? "" : " opacity-50"}">
              <label class="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5">
                <input type="checkbox" name="${prefix}[discounts]" value="${discount.id}"${
                  checkedDiscounts.has(discount.id) ? " checked" : ""
                }${eligible ? "" : " disabled"} class="h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600" />
                <span class="min-w-0 truncate text-[14px] text-slate-800">${discount.name}</span>
              </label>
              <span data-home-set-badge class="hidden shrink-0 rounded bg-sky-100 px-1.5 py-0.5 text-[11px] font-semibold text-sky-800">光セット連動</span>
              ${mainBlocked ? '<span class="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">主回線対象外</span>' : ""}
              <span data-ineligible-badge class="shrink-0 rounded bg-slate-200 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600${eligible ? " hidden" : ""}">対象外</span>
              <span data-discount-amount class="shrink-0 text-[14px] font-semibold text-emerald-700">-${Number(amount).toLocaleString("ja-JP")}円/月</span>
              ${helpTipButton(`適用される条件：${discount.condition || "条件の記載がありません"}`)}
            </div>`;
        })
        .join("")
    : `<p class="rounded-lg border border-slate-200 px-3 py-3 text-[14px] text-slate-500">定額プランのため割引なし</p>`;

  const html = `
    <div data-line-panel="${lineIndex}" class="rounded-xl border border-slate-200 p-4 sm:p-5${lineIndex === getActiveLineIndex() ? "" : " hidden"}">
      <div class="mb-2 border-b border-slate-100 pb-2">
        <h3 class="text-[16px] font-bold text-slate-900">${carrier.name} — ${lineLabel(lineIndex)}</h3>
        <a href="${carrier.official_url}" target="_blank" rel="noopener noreferrer" class="mt-1 inline-flex items-center gap-0.5 text-[12px] text-slate-500 transition hover:text-blue-600 hover:underline">公式料金ページ <span aria-hidden="true">↗</span></a>
      </div>
      <div data-carrier-plans class="mb-5">
        <div class="mb-1.5 flex items-center justify-between gap-2">
          <p class="text-[15px] font-semibold text-slate-700">料金プラン</p>
          <button type="button" data-auto-plan-line="${lineIndex}" class="text-[13px] font-medium text-blue-600 hover:underline${planManual ? "" : " hidden"}">自動選択に戻す</button>
        </div>
        <div class="space-y-2">${plansHtml}</div>
        ${renderPlanComparisonNotes(carrier)}
      </div>
      <details class="advanced-details mt-4" data-advanced-details="line-discounts-${lineIndex}">
        <summary class="advanced-details__summary">
          <span class="advanced-details__title">詳細条件（任意）</span>
          <span class="advanced-details__hint">割引・家族割などの詳細条件</span>
        </summary>
        <div class="advanced-details__body mt-3">
          <p class="mb-2 text-[15px] font-semibold text-slate-700">割引</p>
          <div class="space-y-2">${discountsHtml}</div>
        </div>
      </details>
    </div>`;

  if (panel) {
    panel.outerHTML = html;
  } else {
    container.insertAdjacentHTML("beforeend", html);
  }
}

function renderLineCard(lineIndex, carrierId = DEFAULT_CARRIER) {
  const prefix = linePrefix(lineIndex);
  const borderClass =
    lineIndex === 0 ? "border-blue-200 bg-blue-50/40" : "border-slate-200 bg-white";
  const fieldClass =
    "h-11 w-full max-w-full rounded-lg border border-slate-300 bg-white px-3 text-[14px] text-slate-800 placeholder:text-slate-400";
  const labelClass = "mb-1.5 block text-[14px] font-semibold text-slate-600";
  const hiddenClass = lineIndex === getActiveLineIndex() ? "" : " hidden";
  const mainBadge =
    lineIndex === 0
      ? '<span class="rounded-full bg-blue-100 px-2.5 py-0.5 text-[11px] font-semibold text-blue-800">主回線</span>'
      : "";

  return `
    <article data-line-card="${lineIndex}" class="rounded-xl border px-4 py-4 sm:px-5 ${borderClass}${hiddenClass}">
      <div class="mb-2 flex items-start justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-[15px] font-semibold text-slate-900">回線${lineIndex + 1}</span>
          ${mainBadge}
          <span class="line-card-total" data-line-total="${lineIndex}"></span>
        </div>
        ${lineIndex > 0 ? `<button type="button" data-remove-line="${lineIndex}" class="shrink-0 rounded-md px-2 py-1 text-[13px] font-medium text-red-600 hover:bg-red-50">削除</button>` : ""}
      </div>
      <div class="mb-4">
        <p class="${labelClass}">携帯会社</p>
        ${renderCarrierRadios(lineIndex, carrierId)}
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="${labelClass}" for="line-${lineIndex}-age">年齢</label>
          <div class="input-with-unit">
            <input id="line-${lineIndex}-age" type="number" name="${prefix}[age]" min="0" max="120" placeholder="35" class="${fieldClass}" />
            <span class="input-unit">歳</span>
          </div>
        </div>
        <div>
          <label class="${labelClass}" for="line-${lineIndex}-data">データ使用量</label>
          <div class="flex items-center gap-2">
            <div class="input-with-unit min-w-0 flex-1">
              <input id="line-${lineIndex}-data" type="number" name="${prefix}[data_usage]" min="0" max="10000" placeholder="10" class="${fieldClass}" />
              <span class="input-unit">GB</span>
            </div>
            <label class="inline-flex shrink-0 cursor-pointer items-center gap-1.5 text-[12px] text-slate-600">
              <input type="checkbox" name="${prefix}[data_unlimited]" value="1" class="rounded border-slate-300 text-blue-600" data-line-unlimited="${lineIndex}" />
              無制限
            </label>
          </div>
        </div>
      </div>
      ${renderAdvancedDetails(
        `line-${lineIndex}`,
        "カード・決済・セット割などの詳細条件",
        `<p class="mb-3 text-[12px] leading-relaxed text-slate-500">カード・固定回線・ポイント利用などを設定すると、より実際の料金に近い比較ができます</p>
        <div data-line-payment-sections>
          ${renderLinePayPayCardSection(lineIndex, CARRIER_UI[carrierId] || {}, prefix, CARRIERS_BY_ID[carrierId]?.name || "この回線")}
          ${renderLineQrSection(lineIndex, CARRIER_UI[carrierId] || {}, prefix)}
        </div>`
      )}
    </article>`;
}

function updateLinePaymentSections(lineIndex) {
  const card = document.querySelector(`[data-line-card="${lineIndex}"]`);
  const mount = card?.querySelector("[data-line-payment-sections]");
  if (!mount) return;

  const state = readLineState(lineIndex);
  const carrierId = getLineCarrier(lineIndex);
  const prefix = linePrefix(lineIndex);
  const ui = CARRIER_UI[carrierId] || {};

  mount.innerHTML =
    renderLinePayPayCardSection(lineIndex, ui, prefix, CARRIERS_BY_ID[carrierId]?.name || "この回線") +
    renderLineQrSection(lineIndex, ui, prefix);

  setValueForLine(lineIndex, "qr_paypay", state.qr_paypay);
  setValueForLine(lineIndex, "qr_dbarai", state.qr_dbarai);
  setValueForLine(lineIndex, "qr_aupay", state.qr_aupay);
  setValueForLine(lineIndex, "au_jibun_bank_balance", state.au_jibun_bank_balance);
  const paypayCardTier = form.querySelector(`[name="${linePrefix(lineIndex)}[paypay_card_tier]"]`);
  if (paypayCardTier) paypayCardTier.value = state.paypay_card_tier || "";
  const dcardTier = form.querySelector(`[name="${linePrefix(lineIndex)}[dcard_tier]"]`);
  if (dcardTier) dcardTier.value = state.dcard_tier || "standard";
  setCheckedForLine(lineIndex, "paypay_gold_linked", state.paypay_gold_linked);
  setCheckedForLine(lineIndex, "aupay_gold", state.aupay_gold);
  setCheckedForLine(lineIndex, "docomo_bill_dcard", state.docomo_bill_dcard);
  setCheckedForLine(lineIndex, "au_pay_card_bank_is_jibun", state.au_pay_card_bank_is_jibun);
  const auBillMode = form.querySelector(`[name="${linePrefix(lineIndex)}[au_bill_payment_mode]"]`);
  if (auBillMode) auBillMode.value = state.au_bill_payment_mode || "other";
  syncLineCardUiVisibility(lineIndex);
}

function setValueForLine(lineIndex, name, value) {
  const input = form.querySelector(`[name="${linePrefix(lineIndex)}[${name}]"]`);
  if (input && value !== "") input.value = value;
}

function setCheckedForLine(lineIndex, name, checked) {
  const input = form.querySelector(`[name="${linePrefix(lineIndex)}[${name}]"]`);
  if (input) input.checked = checked;
}

function readLineState(lineIndex) {
  const prefix = linePrefix(lineIndex);
  const unlimited = Boolean(form.querySelector(`[name="${prefix}[data_unlimited]"]`)?.checked);

  return {
    carrier: getLineCarrier(lineIndex),
    age: form.querySelector(`[name="${prefix}[age]"]`)?.value || "",
    data_usage: unlimited ? "unlimited" : form.querySelector(`[name="${prefix}[data_usage]"]`)?.value || "10",
    data_unlimited: unlimited,
    plan: readManualPlanId(lineIndex),
    discounts: [...readCheckedDiscounts(lineIndex)],
    qr_paypay: form.querySelector(`[name="${prefix}[qr_paypay]"]`)?.value || "",
    qr_dbarai: form.querySelector(`[name="${prefix}[qr_dbarai]"]`)?.value || "",
    qr_aupay: form.querySelector(`[name="${prefix}[qr_aupay]"]`)?.value || "",
    paypay_card_tier: form.querySelector(`[name="${prefix}[paypay_card_tier]"]`)?.value || "",
    paypay_gold_linked: Boolean(form.querySelector(`[name="${prefix}[paypay_gold_linked]"]`)?.checked),
    aupay_gold: Boolean(form.querySelector(`[name="${prefix}[aupay_gold]"]`)?.checked),
    au_bill_payment_mode:
      form.querySelector(`[name="${prefix}[au_bill_payment_mode]"]`)?.value || "other",
    au_pay_card_bank_is_jibun: Boolean(
      form.querySelector(`[name="${prefix}[au_pay_card_bank_is_jibun]"]`)?.checked
    ),
    docomo_bill_dcard: Boolean(form.querySelector(`[name="${prefix}[docomo_bill_dcard]"]`)?.checked),
    au_jibun_bank_balance: form.querySelector(`[name="${prefix}[au_jibun_bank_balance]"]`)?.value || "",
    dcard_tier: form.querySelector(`[name="${prefix}[dcard_tier]"]`)?.value || "standard",
  };
}

function setLineFormFields(lineIndex, state) {
  const prefix = linePrefix(lineIndex);
  const setValue = (name, value) => {
    const input = form.querySelector(`[name="${prefix}[${name}]"]`);
    if (input && value !== "") input.value = value;
  };
  const setChecked = (name, checked) => {
    const input = form.querySelector(`[name="${prefix}[${name}]"]`);
    if (input) input.checked = checked;
  };

  const carrierRadio = form.querySelector(`input[name="${prefix}[carrier]"][value="${state.carrier}"]`);
  if (carrierRadio) carrierRadio.checked = true;

  setValue("age", state.age);
  setChecked("data_unlimited", state.data_unlimited);
  const dataInput = form.querySelector(`[name="${prefix}[data_usage]"]`);
  if (dataInput) {
    dataInput.value = state.data_unlimited ? "" : state.data_usage;
    dataInput.disabled = state.data_unlimited;
  }

  setValue("qr_paypay", state.qr_paypay);
  setValue("qr_dbarai", state.qr_dbarai);
  setValue("qr_aupay", state.qr_aupay);
  setValue("au_jibun_bank_balance", state.au_jibun_bank_balance);
  const paypayCardTier = form.querySelector(`[name="${prefix}[paypay_card_tier]"]`);
  if (paypayCardTier) paypayCardTier.value = state.paypay_card_tier || "";
  setChecked("paypay_gold_linked", state.paypay_gold_linked);
  setChecked("aupay_gold", state.aupay_gold);
  setChecked("docomo_bill_dcard", state.docomo_bill_dcard);
  setChecked("au_pay_card_bank_is_jibun", state.au_pay_card_bank_is_jibun);
  const auBillMode = form.querySelector(`[name="${prefix}[au_bill_payment_mode]"]`);
  if (auBillMode) auBillMode.value = state.au_bill_payment_mode || "other";
  const dcardTier = form.querySelector(`[name="${prefix}[dcard_tier]"]`);
  if (dcardTier) dcardTier.value = state.dcard_tier;

  if (state.plan) {
    const planInput = form.querySelector(`[name="${prefix}[plan]"][value="${state.plan}"]`);
    if (planInput) planInput.checked = true;
  }
  form.querySelectorAll(`[name="${prefix}[discounts]"]`).forEach((input) => {
    input.checked = state.discounts.includes(input.value);
  });
}

function setLinePlanDiscountFields(lineIndex, state) {
  const prefix = linePrefix(lineIndex);
  if (state.plan) {
    const planInput = form.querySelector(`[name="${prefix}[plan]"][value="${state.plan}"]`);
    if (planInput) planInput.checked = true;
  }
  form.querySelectorAll(`[name="${prefix}[discounts]"]`).forEach((input) => {
    input.checked = state.discounts.includes(input.value);
  });
}

function applyLineState(lineIndex, state) {
  const linesContainer = document.getElementById("lines-container");
  const existingCard = document.querySelector(`[data-line-card="${lineIndex}"]`);
  const cardHtml = renderLineCard(lineIndex, state.carrier);
  if (existingCard) {
    existingCard.outerHTML = cardHtml;
  } else if (linesContainer) {
    linesContainer.insertAdjacentHTML("beforeend", cardHtml);
  }
  renderLineCampaignPanel(CARRIERS_BY_ID[state.carrier], lineIndex, null);
  setLineFormFields(lineIndex, state);
}

function syncAddLineButton() {
  const button = document.getElementById("add-line-button");
  if (!button) return;
  const atMax = getLineIndices().length >= MAX_LINES;
  button.disabled = atMax;
  button.title = atMax ? `最大${MAX_LINES}回線まで追加できます` : "";
}

function compactLineIndices(preferredActive) {
  const indices = getLineIndices();
  const linesContainer = document.getElementById("lines-container");
  const panelsContainer = document.getElementById("campaign-panels");
  if (!linesContainer || !panelsContainer || !indices.length) return;

  const states = indices.map((index) => readLineState(index));
  linesContainer.innerHTML = "";
  panelsContainer.innerHTML = "";

  states.forEach((state, newIndex) => {
    applyLineState(newIndex, state);
  });

  syncAllUiVisibility();
  syncLineDataUsageInputs();

  const newActive =
    preferredActive != null
      ? Math.min(Math.max(0, preferredActive), states.length - 1)
      : Math.min(getActiveLineIndex(), states.length - 1);
  showLinePanel(newActive);
  renderLineTabs();
  syncAddLineButton();
}

function addLine() {
  const indices = getLineIndices();
  if (indices.length >= MAX_LINES) return;
  const nextIndex = indices.length;
  const defaultCarrier = indices.length ? getLineCarrier(indices[indices.length - 1]) : DEFAULT_CARRIER;
  document.getElementById("lines-container")?.insertAdjacentHTML("beforeend", renderLineCard(nextIndex, defaultCarrier));
  renderLineCampaignPanel(CARRIERS_BY_ID[defaultCarrier], nextIndex, null);
  renderLineTabs();
  showLinePanel(nextIndex);
  syncLineCardUiVisibility(nextIndex);
  syncAccountFieldVisibility();
  syncLineDataUsageInputs();
  syncAddLineButton();
  recalculate();
}

function removeLine(lineIndex) {
  if (lineIndex === 0) return;

  const activeOld = getActiveLineIndex();
  let preferredActive = activeOld;
  if (activeOld === lineIndex) {
    preferredActive = lineIndex - 1;
  } else if (activeOld > lineIndex) {
    preferredActive = activeOld - 1;
  }

  document.querySelector(`[data-line-card="${lineIndex}"]`)?.remove();
  document.querySelector(`[data-line-panel="${lineIndex}"]`)?.remove();
  compactLineIndices(preferredActive);
  recalculate();
}

function displayMonthlyTotal(result) {
  return result.value_adjusted_total;
}

function renderCompactLineCard(result) {
  const theme = result.theme || DEFAULT_THEME;
  const monthly = displayMonthlyTotal(result);
  const annual =
    result.value_adjusted_annual != null ? formatYen(result.value_adjusted_annual) : null;

  return `
    <article class="price-card shadow-sm">
      <div class="price-card__body">
        <span class="price-card__accent ${theme.border} border-l-[3px]" aria-hidden="true"></span>
        <div class="price-card__info">
          <div class="price-card__headline">
            <span class="price-card__carrier">${result.carrier_name}</span>
            <span class="price-card__line-label">${result.line_label}</span>
          </div>
          <div class="price-card__subline">
            <span class="price-card__plan truncate" data-tip="${result.plan.name}">${result.plan.name}</span>
            ${annual ? `<span class="price-card__annual">年間 ${annual}</span>` : ""}
          </div>
        </div>
        <div class="price-card__amount-block">
          <span class="price-card__amount">${formatYen(monthly)}</span>
          <span class="price-card__amount-suffix">/月</span>
        </div>
      </div>
    </article>`;
}

function renderPriceCards(results) {
  const container = document.getElementById("price-cards");
  if (!container) return;
  const list = results || [];
  container.classList.toggle("price-cards--single", list.length === 1);
  container.innerHTML = list.map((result) => renderCompactLineCard(result)).join("");
}

function updatePlanHighlight(results) {
  const byLine = Object.fromEntries(results.map((result) => [result.line_index, result]));
  document.querySelectorAll("[data-plan-row]").forEach((row) => {
    const lineIndex = Number(row.dataset.planLine);
    const result = byLine[lineIndex];
    const planId = row.dataset.planId;
    const isSelected = Boolean(result && result.plan.id === planId);
    const isManual = Boolean(isSelected && result.plan_manual);
    const isShort = Boolean(isSelected && result.plan_under_capacity);

    row.classList.toggle("border-blue-200", isSelected && !isShort);
    row.classList.toggle("bg-blue-50", isSelected && !isShort);
    row.classList.toggle("border-slate-200", !isSelected);
    row.classList.toggle("bg-white", !isSelected);
    row.classList.toggle("border-amber-300", isShort);
    row.classList.toggle("bg-amber-50", isShort);

    row.querySelector("[data-plan-marker]")?.classList.toggle("bg-blue-600", isSelected && !isShort);
    row.querySelector("[data-plan-auto-badge]")?.classList.toggle("hidden", !isSelected || isManual);
    row.querySelector("[data-plan-manual-badge]")?.classList.toggle("hidden", !isManual);
    row.querySelector("[data-plan-short-badge]")?.classList.toggle("hidden", !isShort);

    const radio = row.querySelector('input[type="radio"]');
    if (radio) radio.checked = isManual;

    document.querySelectorAll(`[data-auto-plan-line="${lineIndex}"]`).forEach((button) => {
      button.classList.toggle("hidden", !isManual);
    });

    const quote = result?.plan_quotes?.[planId];
    const effectiveEl = row.querySelector("[data-plan-effective]");
    if (effectiveEl) {
      const showEffective = Boolean(quote && quote.qr_points > 0);
      effectiveEl.textContent = showEffective ? `実質 ${formatYen(quote.effective_total)}` : "";
      effectiveEl.classList.toggle("hidden", !showEffective);
    }
  });
}

function updateDiscountEligibility(results) {
  results.forEach((result) => {
    const amounts = result.resolved_discount_amounts || {};
    Object.entries(result.discount_eligibility || {}).forEach(([discountId, eligible]) => {
      const row = document.querySelector(`[data-discount-row="${result.line_index}:${discountId}"]`);
      if (!row) return;
      const mainBlocked = isFamilyDiscountBlockedForResult(result, discountId);
      const showEligible = eligible && !mainBlocked;
      row.classList.toggle("opacity-50", !showEligible);
      row.querySelector('input[type="checkbox"]').disabled = !showEligible;
      row.querySelector("[data-ineligible-badge]")?.classList.toggle("hidden", showEligible);
      const amountEl = row.querySelector("[data-discount-amount]");
      if (amountEl && amounts[discountId] !== undefined) {
        amountEl.textContent = `-${Number(amounts[discountId]).toLocaleString("ja-JP")}円/月`;
      }
    });
  });
}

function updateLineCardTotals(results) {
  results.forEach((result) => {
    const node = document.querySelector(`[data-line-total="${result.line_index}"]`);
    if (node) node.textContent = `${formatYen(result.value_adjusted_total)}/月`;
  });
}

function syncCurrentContractFields() {
  const carrierSelect = form.querySelector('[name="current_carrier"]');
  const planSelect = form.querySelector('[name="current_plan"]');
  const priceInput = form.querySelector('[name="current_price"]');
  const hint = document.getElementById("current-hint");
  if (!carrierSelect || !planSelect) return;

  const carrierId = carrierSelect.value;
  planSelect.disabled = !carrierId;

  planSelect.querySelectorAll("optgroup[data-carrier], option[data-carrier]").forEach((node) => {
    const visible = node.dataset.carrier === carrierId;
    node.hidden = !visible;
    if (node.tagName === "OPTION" && !visible && node.selected) {
      node.selected = false;
    }
  });

  if (hint) {
    const hasPlan = Boolean(planSelect.value);
    const hasPrice = Boolean(priceInput?.value?.trim());
    hint.classList.toggle("hidden", !carrierId || hasPlan || hasPrice);
  }
}

function renderPriceTotal(comparison) {
  const monthly = document.getElementById("grand-total-monthly");
  const annual = document.getElementById("grand-total-annual");
  if (!monthly || !annual) return;

  const lines = comparison?.lines || [];
  const totals = comparison?.totals || {};
  const totalMonthly =
    totals.value_adjusted_total ??
    lines.reduce((sum, line) => sum + (Number(line.value_adjusted_total) || 0), 0);
  const totalAnnual = totals.value_adjusted_annual ?? totalMonthly * 12;

  monthly.textContent = formatYen(totalMonthly);
  annual.textContent = `年間 ${formatYen(totalAnnual)}`;
}

function applyComparison(comparison) {
  syncPaymentCardDiscounts();
  (comparison.lines || []).forEach((result) => {
    const carrier = CARRIERS_BY_ID[result.carrier_id];
    renderLineCampaignPanel(carrier, result.line_index, result);
  });
  renderLineTabs();
  showLinePanel(comparison.active_line_index ?? getActiveLineIndex());
  renderPriceCards(comparison.lines);
  renderPriceTotal(comparison);
  updateLineCardTotals(comparison.lines);
  updatePlanHighlight(comparison.lines);
  updateDiscountEligibility(comparison.lines);
  syncAllUiVisibility();
  updateHomeSetLinkedBadges();
  syncAddLineButton();
}

function updateHomeSetLinkedBadges() {
  Object.keys(HOME_SET_GROUPS).forEach((groupId) => {
    const master = form.querySelector(`input[name="home_set_${groupId}"]`);
    const linked = Boolean(master?.checked);
    document.querySelectorAll(`[data-home-set-group="${groupId}"]`).forEach((row) => {
      row.querySelector("[data-home-set-badge]")?.classList.toggle("hidden", !linked);
    });
  });
}

function syncHomeSetDiscounts() {
  Object.entries(HOME_SET_GROUPS).forEach(([groupId, { discounts }]) => {
    const master = form.querySelector(`input[name="home_set_${groupId}"]`);
    if (!master) return;
    getLineIndices().forEach((lineIndex) => {
      const carrierId = getLineCarrier(lineIndex);
      const discountId = discounts[carrierId];
      if (!discountId) return;
      const input = form.querySelector(`[name="${linePrefix(lineIndex)}[discounts]"][value="${discountId}"]`);
      if (!input || input.disabled) return;
      input.checked = master.checked;
    });
  });
  updateHomeSetLinkedBadges();
}

function readTenureYears() {
  const input = form.querySelector('[name="tenure_years"]');
  if (!input || input.value.trim() === "") return null;
  const value = Number(input.value);
  return Number.isFinite(value) ? value : null;
}

function shouldAutoApplyDiscount(carrierId, discountId) {
  if (MANUAL_OPT_IN_DISCOUNT_IDS.has(discountId)) return false;
  const tenureRule = TENURE_AUTO_DISCOUNTS[carrierId];
  if (tenureRule?.discount_id === discountId) return false;
  return true;
}

function setAutoDiscountCheckbox(input, shouldApply, autoFlag) {
  if (!input || input.disabled || input.dataset.userTouched === "true") return false;
  const changed = input.checked !== shouldApply;
  if (shouldApply) {
    input.checked = true;
    input.dataset[autoFlag] = "1";
  } else if (input.dataset[autoFlag] === "1") {
    input.checked = false;
    input.dataset[autoFlag] = "0";
  }
  return changed;
}

function resolveAllExclusiveDiscounts() {
  getLineIndices().forEach((lineIndex) => {
    [...form.querySelectorAll(`[name="${linePrefix(lineIndex)}[discounts]"]:checked`)].forEach((input) => {
      syncExclusiveDiscounts(input);
    });
  });
}

function syncPaymentCardDiscount(input, shouldApply) {
  if (!input || input.disabled || input.dataset.userTouched === "true") return false;
  const changed = input.checked !== shouldApply;
  if (shouldApply) {
    input.checked = true;
    input.dataset.paymentAuto = "1";
  } else if (input.checked) {
    input.checked = false;
    input.dataset.paymentAuto = "0";
  }
  return changed;
}

function syncPaymentCardDiscounts() {
  let changed = false;
  getLineIndices().forEach((lineIndex) => {
    const prefix = linePrefix(lineIndex);
    const paypayCardTier = form.querySelector(`[name="${prefix}[paypay_card_tier]"]`)?.value || "";
    const docomoBillDcard = Boolean(
      form.querySelector(`[name="${prefix}[docomo_bill_dcard]"]`)?.checked
    );
    const auBillMode =
      form.querySelector(`[name="${prefix}[au_bill_payment_mode]"]`)?.value || "other";

    [
      ["paypay_card", paypayCardTier === "standard"],
      ["paypay_card_gold", paypayCardTier === "gold"],
      ["d_card", docomoBillDcard],
      ["au_pay_card", auBillMode === "au_pay_card"],
    ].forEach(([discountId, shouldApply]) => {
      const input = form.querySelector(`[name="${prefix}[discounts]"][value="${discountId}"]`);
      if (syncPaymentCardDiscount(input, shouldApply)) changed = true;
    });
  });
  if (changed) resolveAllExclusiveDiscounts();
  return changed;
}

function syncEligibleAutoDiscounts(results) {
  let changed = false;
  (results || []).forEach((result) => {
    Object.entries(result.discount_eligibility || {}).forEach(([discountId, eligible]) => {
      const input = form.querySelector(
        `[name="${linePrefix(result.line_index)}[discounts]"][value="${discountId}"]`
      );
      if (!input) return;

      const mainBlocked = isFamilyDiscountBlockedForResult(result, discountId);
      const shouldApply =
        eligible &&
        !mainBlocked &&
        shouldAutoApplyDiscount(result.carrier_id, discountId);

      if (!shouldApply) {
        if (setAutoDiscountCheckbox(input, false, "eligibleAuto")) changed = true;
        return;
      }

      if (setAutoDiscountCheckbox(input, true, "eligibleAuto")) changed = true;
    });
  });

  if (changed) resolveAllExclusiveDiscounts();
  return changed;
}

function syncTenureAutoDiscounts() {
  const tenure = readTenureYears();
  Object.entries(TENURE_AUTO_DISCOUNTS).forEach(([carrierId, rule]) => {
    const shouldApply = tenure !== null && tenure >= rule.min_tenure_years;
    getLineIndices().forEach((lineIndex) => {
      if (getLineCarrier(lineIndex) !== carrierId) return;
      const input = form.querySelector(
        `[name="${linePrefix(lineIndex)}[discounts]"][value="${rule.discount_id}"]`
      );
      if (!input || input.disabled) return;
      if (shouldApply) {
        input.checked = true;
      } else if (input.dataset.tenureAuto === "1") {
        input.checked = false;
      }
      input.dataset.tenureAuto = shouldApply ? "1" : "0";
    });
  });
}

function syncExclusiveDiscounts(changedInput) {
  const match = changedInput.name.match(/^lines\[(\d+)\]\[discounts\]$/);
  if (!match || !changedInput.checked) return;
  const carrierId = getLineCarrier(Number(match[1]));
  const rules = EXCLUSIVE_DISCOUNTS[carrierId];
  if (!rules) return;
  (rules[changedInput.value] || []).forEach((otherId) => {
    const other = form.querySelector(`[name="${linePrefix(match[1])}[discounts]"][value="${otherId}"]`);
    if (other) other.checked = false;
  });
}

function inferHomeSetMastersFromDiscounts() {
  Object.entries(HOME_SET_GROUPS).forEach(([groupId, { discounts }]) => {
    const master = form.querySelector(`input[name="home_set_${groupId}"]`);
    if (!master || master.checked) return;
    const relevantLines = getLineIndices().filter((lineIndex) => discounts[getLineCarrier(lineIndex)]);
    if (relevantLines.length === 0) return;
    const allChecked = relevantLines.every((lineIndex) => {
      const discountId = discounts[getLineCarrier(lineIndex)];
      const input = form.querySelector(`[name="${linePrefix(lineIndex)}[discounts]"][value="${discountId}"]`);
      return input?.checked;
    });
    if (allChecked) master.checked = true;
  });
  updateHomeSetLinkedBadges();
}

function handleLineCarrierChange(lineIndex) {
  const state = readLineState(lineIndex);
  state.carrier = getLineCarrier(lineIndex);
  updateLinePaymentSections(lineIndex);
  renderLineCampaignPanel(CARRIERS_BY_ID[state.carrier], lineIndex, null);
  setLinePlanDiscountFields(lineIndex, state);
  syncLineCardUiVisibility(lineIndex);
  syncAccountFieldVisibility();
  syncTenureAutoDiscounts();
  syncPaymentCardDiscounts();
  renderLineTabs();
  recalculate();
}

let currentController = null;
let recalculatePass = 0;
let lastCalculateOk = true;

async function recalculate() {
  syncAllUiVisibility();
  syncLineDataUsageInputs();
  syncTenureAutoDiscounts();
  syncHomeSetDiscounts();
  syncPaymentCardDiscounts();

  currentController?.abort();
  currentController = new AbortController();
  const { signal } = currentController;

  const cards = document.getElementById("price-cards");
  cards?.setAttribute("aria-busy", "true");
  updateCompareNavigateButton();

  const params = buildParams();

  try {
    const calculateResponse = await fetch(`/api/calculate?${params.toString()}`, { signal });

    if (calculateResponse.status === 400) {
      lastCalculateOk = false;
      showError("入力値が正しくありません。各回線の通信量・年齢などをご確認ください。");
      updateCompareNavigateButton();
      return;
    }
    if (!calculateResponse.ok) throw new Error(`HTTP ${calculateResponse.status}`);

    const comparison = await calculateResponse.json();
    applyComparison(comparison);
    lastCalculateOk = true;

    if (recalculatePass < 2 && syncEligibleAutoDiscounts(comparison.lines)) {
      recalculatePass += 1;
      return recalculate();
    }
    recalculatePass = 0;
    history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
    clearError();
  } catch (error) {
    if (error.name === "AbortError") return;
    lastCalculateOk = false;
    showError("料金の取得に失敗しました。時間をおいて再度お試しください。");
  } finally {
    cards?.setAttribute("aria-busy", "false");
    updateCompareNavigateButton();
  }
}

function updateCompareNavigateButton() {
  const button = document.getElementById("compare-navigate-button");
  if (!button) return;
  const hasError = !document.getElementById("price-error")?.classList.contains("hidden");
  button.disabled = !lastCalculateOk || hasError;
}

function navigateToComparePage() {
  const hasError = !document.getElementById("price-error")?.classList.contains("hidden");
  if (hasError || !lastCalculateOk) return;
  syncAllUiVisibility();
  syncLineDataUsageInputs();
  syncTenureAutoDiscounts();
  syncHomeSetDiscounts();
  syncPaymentCardDiscounts();
  const params = buildParams().toString();
  if (!window.SimulatorState?.saveCompareInput?.(params)) return;
  window.location.assign("/compare");
}

function bootstrapSimulator() {
  syncAllUiVisibility();
  syncCurrentContractFields();
  syncLineDataUsageInputs();
  syncAddLineButton();
  inferHomeSetMastersFromDiscounts();
  syncTenureAutoDiscounts();
  syncHomeSetDiscounts();
  syncPaymentCardDiscounts();
  renderLineTabs();
  updateCompareNavigateButton();
  const initial = readInitialComparison();
  if (initial) {
    applyComparison(initial);
    lastCalculateOk = document.getElementById("price-error")?.classList.contains("hidden") ?? true;
    if (syncEligibleAutoDiscounts(initial.lines)) {
      recalculate();
      return;
    }
  }
  recalculate();
}

function readInitialComparison() {
  const node = document.getElementById("initial-comparison");
  if (!node) return null;
  try {
    return JSON.parse(node.textContent);
  } catch {
    return null;
  }
}

if (form) {
  let debounceTimer = null;
  form.addEventListener("change", (event) => {
    if (event.target.matches('[name="current_carrier"], [name="current_plan"]')) {
      syncCurrentContractFields();
      recalculate();
      return;
    }
    const carrierMatch = event.target.name?.match(/^lines\[(\d+)\]\[carrier\]$/);
    if (carrierMatch) {
      handleLineCarrierChange(Number(carrierMatch[1]));
      return;
    }
    if (event.target.matches('[name$="[discounts]"]')) markDiscountUserTouched(event.target);
    if (
      event.target.matches(
        '[name$="[paypay_card_tier]"], [name$="[au_bill_payment_mode]"], [name$="[docomo_bill_dcard]"], [name$="[aupay_gold]"]'
      )
    ) {
      syncPaymentCardDiscounts();
      recalculate();
      return;
    }
  });
  form.addEventListener("input", (event) => {
    if (event.target.name === "current_price") {
      syncCurrentContractFields();
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(recalculate, 250);
      return;
    }
    if (event.target.name?.startsWith("home_set_")) syncHomeSetDiscounts();
    if (event.target.name === "tenure_years") syncTenureAutoDiscounts();
    if (
      event.target.matches('[name$="[au_bill_payment_mode]"], [name$="[docomo_bill_dcard]"]')
    ) {
      syncPaymentCardDiscounts();
    }
    if (event.target.matches('[name$="[discounts]"]')) syncExclusiveDiscounts(event.target);
    if (event.target.dataset.lineUnlimited !== undefined) syncLineDataUsageInputs();
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(recalculate, 250);
  });
  form.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-line-tab]");
    if (tab) {
      showLinePanel(Number(tab.dataset.lineTab));
      return;
    }
    if (event.target.id === "add-line-button") {
      addLine();
      return;
    }
    const remove = event.target.closest("[data-remove-line]");
    if (remove) {
      removeLine(Number(remove.dataset.removeLine));
      return;
    }
    if (event.target.id === "compare-navigate-button") {
      navigateToComparePage();
      return;
    }
    const reset = event.target.closest("[data-auto-plan-line]");
    if (reset) {
      const lineIndex = reset.dataset.autoPlanLine;
      form.querySelectorAll(`[name="${linePrefix(lineIndex)}[plan]"]`).forEach((input) => {
        input.checked = false;
      });
      recalculate();
    }
  });
  form.addEventListener("submit", (event) => event.preventDefault());
  bootstrapSimulator();
}

const tooltip = document.createElement("div");
tooltip.className = "pointer-events-none fixed z-50 hidden max-w-xs whitespace-pre-line rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-lg";
document.body.appendChild(tooltip);

document.addEventListener("mouseover", (event) => {
  const trigger = event.target.closest("[data-tip]");
  if (!trigger) return;
  tooltip.textContent = trigger.getAttribute("data-tip") || "";
  tooltip.classList.remove("hidden");
  const anchor = trigger.getBoundingClientRect();
  tooltip.style.left = `${anchor.left}px`;
  tooltip.style.top = `${anchor.top - tooltip.offsetHeight - 6}px`;
});
document.addEventListener("mouseout", (event) => {
  if (event.target.closest("[data-tip]")) tooltip.classList.add("hidden");
});
