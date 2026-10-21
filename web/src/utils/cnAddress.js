const _trim = (v) => String(v ?? '').trim()

const _PROVINCES = [
  { full: '北京', aliases: ['北京', '北京市'] },
  { full: '天津', aliases: ['天津', '天津市'] },
  { full: '上海', aliases: ['上海', '上海市'] },
  { full: '重庆', aliases: ['重庆', '重庆市'] },
  { full: '河北省', aliases: ['河北', '河北省'] },
  { full: '山西省', aliases: ['山西', '山西省'] },
  { full: '辽宁省', aliases: ['辽宁', '辽宁省'] },
  { full: '吉林省', aliases: ['吉林', '吉林省'] },
  { full: '黑龙江省', aliases: ['黑龙江', '黑龙江省'] },
  { full: '江苏省', aliases: ['江苏', '江苏省'] },
  { full: '浙江省', aliases: ['浙江', '浙江省'] },
  { full: '安徽省', aliases: ['安徽', '安徽省'] },
  { full: '福建省', aliases: ['福建', '福建省'] },
  { full: '江西省', aliases: ['江西', '江西省'] },
  { full: '山东省', aliases: ['山东', '山东省'] },
  { full: '河南省', aliases: ['河南', '河南省'] },
  { full: '湖北省', aliases: ['湖北', '湖北省'] },
  { full: '湖南省', aliases: ['湖南', '湖南省'] },
  { full: '广东省', aliases: ['广东', '广东省'] },
  { full: '海南省', aliases: ['海南', '海南省'] },
  { full: '四川省', aliases: ['四川', '四川省'] },
  { full: '贵州省', aliases: ['贵州', '贵州省'] },
  { full: '云南省', aliases: ['云南', '云南省'] },
  { full: '陕西省', aliases: ['陕西', '陕西省'] },
  { full: '甘肃省', aliases: ['甘肃', '甘肃省'] },
  { full: '青海省', aliases: ['青海', '青海省'] },
  { full: '内蒙古自治区', aliases: ['内蒙古', '内蒙古自治区'] },
  { full: '广西壮族自治区', aliases: ['广西', '广西壮族自治区'] },
  { full: '西藏自治区', aliases: ['西藏', '西藏自治区'] },
  { full: '宁夏回族自治区', aliases: ['宁夏', '宁夏回族自治区'] },
  { full: '新疆维吾尔自治区', aliases: ['新疆', '新疆维吾尔自治区'] },
  { full: '香港特别行政区', aliases: ['香港', '香港特别行政区'] },
  { full: '澳门特别行政区', aliases: ['澳门', '澳门特别行政区'] },
  { full: '台湾省', aliases: ['台湾', '台湾省'] },
]

const _ALIAS_INDEX = (() => {
  const list = []
  for (const p of _PROVINCES) {
    for (const a of p.aliases) {
      list.push({ alias: a, full: p.full })
    }
  }
  list.sort((x, y) => y.alias.length - x.alias.length)
  return list
})()

const _isMunicipality = (province) => province === '北京' || province === '天津' || province === '上海' || province === '重庆'

const _NO_DISTRICT_CITIES = new Set(['东莞市', '中山市', '儋州市', '嘉峪关市', '三沙市'])

const _STREET_LIKE_RE = /(镇|街道|乡|路|街|道|巷|弄|村|社区|大道|广场)$/u

const _DISTRICT_SUFFIX_RE = /(自治县|旗|区|县|市|林区|矿区|特区|新区|镇|街道|乡)$/u

const _stripLeadingAdminSuffix = (s) => {
  let out = String(s || '')
  for (;;) {
    const next = out.replace(/^(省|市|自治区|特别行政区|壮族|回族|维吾尔|藏)/u, '')
    if (next === out) break
    out = next
  }
  return out
}

const _matchProvince = (firstSegment) => {
  const s = _trim(firstSegment)
  if (!s) return { province: '', rest: '' }
  for (const it of _ALIAS_INDEX) {
    if (s.startsWith(it.alias)) {
      const rest = _stripLeadingAdminSuffix(s.slice(it.alias.length))
      return { province: it.full, rest: _trim(rest) }
    }
  }
  return { province: '', rest: '' }
}

const _normalizeCity = (rawCity, province) => {
  const s = _trim(rawCity)
  if (!s) return ''
  if (province === '新疆维吾尔自治区') {
    const m = {
      喀什: '喀什地区',
      阿克苏: '阿克苏地区',
      和田: '和田地区',
      吐鲁番: '吐鲁番市',
      哈密: '哈密市',
      伊犁: '伊犁哈萨克自治州',
      昌吉: '昌吉回族自治州',
      博尔塔拉: '博尔塔拉蒙古自治州',
      巴音郭楞: '巴音郭楞蒙古自治州',
      克孜勒苏: '克孜勒苏柯尔克孜自治州',
    }
    if (m[s]) return m[s]
  }
  if (s.endsWith('市')) return s
  if (s.endsWith('地区')) return s
  if (s.endsWith('盟')) return s
  if (s.endsWith('自治州')) return s
  return `${s}市`
}

const _normalizeDistrict = (rawDistrict, nextSeg) => {
  const s = _trim(rawDistrict)
  if (!s) return ''
  if (_DISTRICT_SUFFIX_RE.test(s)) return s
  const next = _trim(nextSeg)
  if (next && _STREET_LIKE_RE.test(next)) return `${s}市`
  return `${s}区`
}

export const parseCnDotAddress = (input) => {
  const raw = _trim(input)
  if (!raw) return { province: '', city: '', district: '', street: '' }

  const normalized = raw.replace(/[•，,]/g, '·')
  const segs = normalized
    .split('·')
    .map(_trim)
    .filter(Boolean)

  if (!segs.length) return { province: '', city: '', district: '', street: '' }

  const { province, rest } = _matchProvince(segs[0])

  const remaining = []
  if (rest) remaining.push(rest)
  for (const s of segs.slice(1)) remaining.push(s)

  if (!province) {
    return { province: '', city: '', district: '', street: remaining.join(' · ') }
  }

  if (_isMunicipality(province)) {
    const district = _normalizeDistrict(remaining[0] || '', remaining[1] || '')
    const street = remaining.slice(1).join(' · ')
    return { province, city: '', district, street }
  }

  const first = remaining[0] || ''
  const second = remaining[1] || ''

  const looksDistrictLevel = _DISTRICT_SUFFIX_RE.test(first)

  if (looksDistrictLevel && !second) {
    const district = _normalizeDistrict(first, '')
    return { province, city: '', district, street: '' }
  }

  let city = ''
  let district = ''
  let streetParts = []

  if (!first) {
    return { province, city: '', district: '', street: '' }
  }

  const cityCandidate = _normalizeCity(first, province)
  if (_NO_DISTRICT_CITIES.has(cityCandidate)) {
    city = cityCandidate
    district = _trim(second)
    streetParts = remaining.slice(2)
    if (district && !_DISTRICT_SUFFIX_RE.test(district)) {
      if (_STREET_LIKE_RE.test(district)) {
        district = district
      } else {
        district = district
      }
    }
    return { province, city, district, street: streetParts.join(' · ') }
  }

  if (/(市|地区|自治州|盟|州)$/u.test(_trim(first)) || second) {
    city = cityCandidate
    if (second) {
      district = _normalizeDistrict(second, remaining[2] || '')
      streetParts = remaining.slice(2)
    }
    return { province, city, district, street: streetParts.join(' · ') }
  }

  city = cityCandidate
  return { province, city, district: '', street: '' }
}

export const formatCnDotAddress = (obj) => {
  const province = _trim(obj?.province)
  const city = _trim(obj?.city)
  const district = _trim(obj?.district)
  const street = _trim(obj?.street)
  return [province, city, district, street].filter(Boolean).join(' · ')
}

export const formatNearbyAddressPlace = (value) => {
  const raw = _trim(value)
  if (!raw) return ''
  const core = raw.replace(/^在\s*/u, '').replace(/\s*附近$/u, '').trim()
  if (!core) return raw
  return `在${core}附近`
}
