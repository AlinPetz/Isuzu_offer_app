export function cents(value) {
  const raw = String(value ?? "").trim();
  if (!/^-?(?:[0-9]{1,12}(?:[.,][0-9]{1,2})?|[.,][0-9]{1,2})$/.test(raw)) return null;
  const [whole, fraction = ""] = raw.replace(/^-/, "").split(/[.,]/);
  const amount = BigInt(whole || "0") * 100n + BigInt(fraction.padEnd(2, "0"));
  return raw.startsWith("-") && amount !== 0n ? null : amount;
}

const integerFormat = new Intl.NumberFormat("ro-RO");

export function formatEUR(amount) {
  return `${integerFormat.format(amount / 100n)},${String(amount % 100n).padStart(2, "0")}\u00a0EUR`;
}

function isPtoItem(name, code) {
  const normalize = value => value.toLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");
  const words = normalize(name).match(/[a-z0-9]+/g) || [];
  const compact = normalize(code || "").replace(/[^a-z0-9]/g, "");
  return words.includes("pto") || words.join(" ").includes("priza de putere") ||
    Boolean(compact && words.join("").includes(compact));
}

export function previewPricing(commercial, rawDiscount, includePto, inputs) {
  const base = cents(commercial.base);
  const transport = cents(commercial.transport);
  const discount = cents(rawDiscount.trim() || "0");
  const ptoPrice = cents(commercial.pto_price);
  const optionals = [];
  let error = "";
  if (discount === null || discount > base) error = "Reducerea trebuie să fie între zero și prețul de bază al șasiului.";
  if (includePto && ptoPrice === null) error = "PTO nu poate fi inclus pentru acest șasiu.";
  let hasPto = includePto;
  for (const input of inputs) {
    const description = input.description.trim();
    const value = input.price.trim();
    if (!description && !value) continue;
    const price = cents(value);
    if (!description || price === null) {
      error ||= "Completați denumirea și prețul fiecărui opțional (maximum două zecimale).";
      continue;
    }
    if (isPtoItem(description, commercial.pto_code)) {
      if (hasPto) error ||= "PTO este inclus de mai multe ori. Eliminați linia duplicată.";
      hasPto = true;
    }
    optionals.push({description, price});
  }
  const pto = includePto ? ptoPrice : 0n;
  const total = error ? null : base + transport - discount + pto +
    optionals.reduce((sum, item) => sum + item.price, 0n);
  return {base, transport, discount, pto, optionals, total, error};
}
