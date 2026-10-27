/**
 * 轻量 Markdown 解析（小程序端）
 *
 * 为什么自己写：模型返回的是带 # / - / ** 的 Markdown，原样塞进 <text> 会把
 * 「###」「**」这类源标记直接显示给用户。这里把它解析成块结构交给页面渲染，
 * 页面上只剩排版好的标题、段落、列表和加粗，看不到任何源标记。
 *
 * 支持：# 标题、段落、- / * 无序列表、1. 有序列表、> 引用、--- 分隔线、
 *      **加粗**、`行内代码`
 * 不支持（也不需要）：图片、链接、表格——表格由后端用结构化数据单独下发。
 */
'use strict'

// 行内：**加粗** 和 `行内代码`
function parseInline(text) {
  const src = text === null || text === undefined ? '' : String(text)
  const segs = []
  const re = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g
  let last = 0
  let m
  while ((m = re.exec(src)) !== null) {
    if (m.index > last) segs.push({ t: src.slice(last, m.index) })
    const tok = m[0]
    if (tok.charAt(0) === '`') segs.push({ t: tok.slice(1, -1), code: true })
    else segs.push({ t: tok.slice(2, -2), b: true })
    last = m.index + tok.length
  }
  if (last < src.length) segs.push({ t: src.slice(last) })
  if (!segs.length) segs.push({ t: '' })
  segs.forEach(function (s, i) { s.i = i })
  return segs
}

// 块级：按行切，认出标题/列表/引用/分隔线，其余合并成段落
function parseBlocks(raw) {
  const lines = String(raw === null || raw === undefined ? '' : raw)
    .replace(/\r\n?/g, '\n')
    .split('\n')
  const blocks = []
  let para = []
  let list = null
  let items = []

  function flushPara() {
    if (!para.length) return
    blocks.push({ type: 'p', segs: parseInline(para.join('\n')) })
    para = []
  }
  function flushList() {
    if (list && items.length) {
      list.items = items.map(function (s, i) {
        return { i: i + 1, segs: parseInline(s) }
      })
      items = []
    }
    if (list) {
      blocks.push(list)
      list = null
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim()
    // 空行只断段落，不断列表：模型常在列表项之间留空行，
    // 断掉的话序号会重新从 1 开始（1、1、1），看着像 bug
    if (!t) { flushPara(); continue }

    // 分隔线 --- *** ___
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) {
      flushPara(); flushList()
      blocks.push({ type: 'hr' })
      continue
    }
    // 标题 # ~ ######（允许「###标题」这种没空格的写法）
    let m = /^(#{1,6})\s*(.*)$/.exec(t)
    if (m) {
      flushPara(); flushList()
      blocks.push({ type: 'h', level: m[1].length, segs: parseInline(m[2]) })
      continue
    }
    // 引用 >
    m = /^>\s?(.*)$/.exec(t)
    if (m) {
      flushPara(); flushList()
      blocks.push({ type: 'quote', segs: parseInline(m[1]) })
      continue
    }
    // 有序列表 1. / 1、 / 1)
    m = /^(\d{1,3})[.、)]\s+(.*)$/.exec(t)
    if (m) {
      flushPara()
      if (!list || list.type !== 'ol') { flushList(); list = { type: 'ol', items: [] } }
      items.push(m[2])
      continue
    }
    // 无序列表 - / * / +
    m = /^[-*+]\s+(.*)$/.exec(t)
    if (m) {
      flushPara()
      if (!list || list.type !== 'ul') { flushList(); list = { type: 'ul', items: [] } }
      items.push(m[1])
      continue
    }
    // 普通段落：段落前要把上一段列表收尾
    flushList()
    para.push(t)
  }
  flushPara()
  flushList()

  blocks.forEach(function (b, i) { b.i = i })
  return blocks
}

// 流式过程中原文是半截的：`**加粗` 还没闭合、标题还没写完。
// 这类残缺标记留在页面上很难看，解析前先按「还没写完」处理掉。
function cleanPartial(raw) {
  let s = String(raw === null || raw === undefined ? '' : raw)
  const stars = s.match(/\*\*/g)
  if (stars && stars.length % 2 === 1) {
    const idx = s.lastIndexOf('**')
    s = s.slice(0, idx)
  }
  // 行尾孤立的 # 标记（标题正在写）
  s = s.replace(/(^|\n)#{1,6}[ \t]*$/, '$1')
  return s
}

/**
 * @param {string} text  原始文本
 * @param {boolean} streaming 是否还在流式生成中
 * @returns {Array} 块数组，每块 { type, segs/items, level, i }
 */
function parse(text, streaming) {
  const src = streaming ? cleanPartial(text) : String(text || '')
  return parseBlocks(src)
}

module.exports = { parse: parse, parseBlocks: parseBlocks, parseInline: parseInline }
