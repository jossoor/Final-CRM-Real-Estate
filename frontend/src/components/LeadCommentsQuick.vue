<template>
  <div class="relative" @click.stop @mousedown.stop @dblclick.stop>
    <!-- العرض المختصر -->
    <div v-if="!open" class="flex items-start justify-between gap-2">
      <div class="whitespace-pre-wrap break-words text-ink-gray-9 min-w-0">
        {{ lastCommentText || __('No FeedBacks yet') }}
      </div>
      <button
        type="button"
        class="px-2 py-1 text-ink-blue-7 underline hover:no-underline"
        @click.stop="toggle(true)"
      >
        {{ __('Add') }}
      </button>
    </div>

    <!-- المودال -->
    <div v-else class="fixed inset-0 z-[100] flex items-start justify-center" @click="onBackdropClick">
      <div class="absolute inset-0 bg-black/30"></div>

      <div
        class="relative mt-16 bg-white border rounded-xl shadow-xl w-[min(720px,calc(100vw-32px))] max-h-[80vh] overflow-auto"
        @click.stop
      >
        <!-- Header -->
        <div class="sticky top-0 z-10 bg-white flex items-center justify-between px-4 pt-4 pb-2 border-b">
          <div class="text-base font-semibold text-ink-gray-9">{{ __('FeedBacks') }}</div>
          <Button variant="subtle" @click.stop="toggle(false)" :label="__('Close')" />
        </div>

        <!-- الجسم -->
        <div class="px-4 pb-24">
          <div class="mt-3 mb-4">
            <div v-if="loading" class="text-ink-gray-5 text-sm">{{ __('Loading...') }}</div>
            <div v-else-if="!comments.length" class="text-ink-gray-6 text-sm">{{ __('No FeedBacks yet') }}</div>
            <div v-else class="space-y-3">
              <div v-for="c in comments" :key="c.name" class="border-b pb-2">
                <!-- Title if available -->
                <div v-if="c.subject" class="font-semibold text-base text-ink-gray-9 mb-1">
                  {{ c.subject }}
                </div>
                <div class="flex flex-wrap items-center justify-between gap-3 text-xs text-ink-gray-6">
                  <div>{{ formatDate(c.creation) }} — {{ c.owner }}</div>
                  <label class="inline-flex items-center gap-1 text-[11px]" :title="__('Delayed flag is read-only')">
                    <input
                      type="checkbox"
                      disabled
                      class="h-3.5 w-3.5 cursor-not-allowed accent-red-500"
                      :checked="isDelayedFlag(c)"
                    />
                    <span>{{ __('Delayed') }}</span>
                  </label>
                </div>

                <div class="whitespace-pre-wrap break-words mt-1">
                  {{ stripHtml(c.content || '') }}
                </div>
              </div>
            </div>
          </div>

          <!-- الفورم (الزر جوّاها) -->
          <form
            class="mt-2"
            @submit.prevent="addComment"
            @keydown.ctrl.enter.prevent="addComment"
            @keydown.meta.enter.prevent="addComment"
          >
            <!-- Title field (optional) -->
            <div class="mb-3">
              <label class="block text-xs text-ink-gray-6 mb-1">
                {{ __('Title (optional)') }}
              </label>
              <input
                v-model="commentTitle"
                type="text"
                :placeholder="__('Enter feedback title...')"
                class="w-full rounded border px-3 py-2 outline-none focus:ring-2 focus:ring-ink-blue-4"
              />
            </div>

            <textarea
              v-model="newComment"
              rows="4"
              :placeholder="__('Write a FeedBack...')"
              class="w-full rounded border px-3 py-2 outline-none focus:ring-2 focus:ring-ink-blue-4"
              required
            />

            <!-- Reminder (إجباري) -->
            <div class="mt-3">
              <label class="block text-xs text-ink-gray-6 mb-1">
                {{ __('Reminder at (required)') }}
              </label>
              <input
                type="datetime-local"
                v-model="reminderAtLocal"
                required
                class="w-[260px] rounded border px-2 py-1 text-sm"
              />
              <p v-if="reminderError" class="mt-1 text-xs text-red-600">
                {{ reminderError }}
              </p>
            </div>

            <!-- Footer داخل الفورم عشان الـ required يشتغل -->
            <div class="sticky bottom-0 bg-white px-0 py-3 mt-4 border-t flex items-center justify-end gap-2">
              <Button
                :disabled="saving || !canSubmit"
                type="submit"
                :label="saving ? __('Saving...') : __('Add FeedBack')"
                variant="solid"
              />
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Button, call, toast } from 'frappe-ui'
import { formatDate } from '@/utils'

const props = defineProps({
  leadName: { type: String, required: true },
})

const open = ref(false)
const loading = ref(false)
const saving  = ref(false)
const comments = ref([])
const newComment = ref('')
const commentTitle = ref('') // Title for the feedback

/** Reminder (required): يبدأ فاضي لإجبار الاختيار */
const reminderAtLocal = ref('') // YYYY-MM-DDTHH:mm
const reminderError = ref('')

/** آخر Reminder على الليد (للعرض أو المنطق لاحقًا) */
const latestReminder = ref(null)

const lastCommentText = computed(() =>
  comments.value.length ? stripHtml(comments.value[0].content || '') : ''
)

const canSubmit = computed(() => {
  if (!newComment.value.trim() || !reminderAtLocal.value) return false
  const dt = toDate(reminderAtLocal.value)
  return dt && dt.getTime() > Date.now()
})

function stripHtml(html) {
  try {
    const div = document.createElement('div')
    div.innerHTML = html || ''
    return (div.textContent || div.innerText || '').trim()
  } catch {
    return html || ''
  }
}

function toDate(localValue) {
  try {
    // input type=datetime-local يرجّع local time بدون timezone
    // بنبني Date(YYYY, M, D, H, m, s) محليًا
    const [date, time] = (localValue || '').split('T')
    if (!date || !time) return null
    const [y, mo, d] = date.split('-').map(x => parseInt(x, 10))
    const [hh, mm] = time.split(':').map(x => parseInt(x, 10))
    return new Date(y, (mo || 1)-1, d, hh || 0, mm || 0, 0, 0)
  } catch {
    return null
  }
}

function toServerDatetime(localValue) {
  // نُحوّل للقالب الذي يقبله السيرفر "YYYY-MM-DD HH:mm:ss"
  const dt = toDate(localValue)
  if (!dt) return ''
  const pad = (n) => String(n).padStart(2, '0')
  const y = dt.getFullYear()
  const m = pad(dt.getMonth()+1)
  const d = pad(dt.getDate())
  const H = pad(dt.getHours())
  const M = pad(dt.getMinutes())
  const S = pad(dt.getSeconds())
  return `${y}-${m}-${d} ${H}:${M}:${S}`
}

function isDelayedFlag(comment) {
  const flag = comment?.delayed
  return flag === 1 || flag === true || flag === '1' || flag === 'Yes'
}

/* ===== Reminders ===== */
async function loadReminders() {
  latestReminder.value = null

  // 1) API الموحّد
  try {
    const res = await call('crm.api.reminders.list_for_doc', {
      doctype: 'CRM Lead',
      name: props.leadName,
    })
    const list = Array.isArray(res?.message) ? res.message : res
    if (Array.isArray(list) && list.length) {
      const sorted = [...list].sort((a, b) => (a.remind_at > b.remind_at ? 1 : -1))
      latestReminder.value = sorted.at(-1)
      return
    }
  } catch (e) {
    // هننزل للفولباك
  }

  // 2) Fallback مباشر على Reminder (الدعم للسكيمتين)
  try {
    const list = await call('frappe.client.get_list', {
      doctype: 'Reminder',
      fields: ['name', 'user', 'description', 'remind_at', 'notified'],
      filters: [
        ['Reminder', 'reference_doctype', '=', 'CRM Lead'],
        ['Reminder', 'reference_name', '=', props.leadName],
      ],
      order_by: 'remind_at asc',
      limit_page_length: 100,
    })
    const arr = Array.isArray(list?.message) ? list.message : list
    if (Array.isArray(arr) && arr.length) {
      latestReminder.value = arr.at(-1)
      return
    }

    // جرّب سكيمة reminder_*
    const list2 = await call('frappe.client.get_list', {
      doctype: 'Reminder',
      fields: ['name', 'user', 'description', 'remind_at', 'notified'],
      filters: [
        ['Reminder', 'reminder_doctype', '=', 'CRM Lead'],
        ['Reminder', 'reminder_docname', '=', props.leadName],
      ],
      order_by: 'remind_at asc',
      limit_page_length: 100,
    })
    const arr2 = Array.isArray(list2?.message) ? list2.message : list2
    if (Array.isArray(arr2) && arr2.length) {
      latestReminder.value = arr2.at(-1)
    }
  } catch (e) {
    // تجاهل
  }
}

/* ===== Comments ===== */
async function refreshDelayedState() {
  try {
    await call('crm.api.reminders.recalc_delayed_for_doc', {
      doctype: 'CRM Lead',
      name: props.leadName,
    })
  } catch (e) {
    // احتمالات: غياب الحقل أو عدم توافر الصلاحيات
    console.debug('recalc_delayed_for_doc failed', e)
  }
}

async function loadComments() {
  loading.value = true
  try {
    const res = await call('frappe.client.get_list', {
      doctype: 'Comment',
      // ملاحظة: لدينا حقل delayed في النظام الحالي + subject للعنوان
      fields: ['name', 'subject', 'content', 'owner', 'creation', 'delayed'],
      filters: {
        reference_doctype: 'CRM Lead',
        reference_name: props.leadName,
        comment_type: 'Comment',
      },
      order_by: 'creation desc',
      limit_page_length: 50,
    })
    comments.value = Array.isArray(res?.message) ? res.message : (Array.isArray(res) ? res : [])
  } finally { loading.value = false }
}

function onBackdropClick(e) { if (e.target === e.currentTarget) toggle(false) }
async function toggle(v) {
  open.value = v
  if (v) {
    reminderError.value = ''
    await refreshDelayedState()
    await Promise.all([loadComments(), loadReminders()])
  }
}

/* ===== Submit ===== */
async function addComment() {
  if (saving.value) return
  const content = newComment.value.trim()
  if (!content) return

  if (!reminderAtLocal.value) {
    reminderError.value = __('Reminder time is required')
    return
  }
  const when = toDate(reminderAtLocal.value)
  if (!when || when.getTime() <= Date.now()) {
    reminderError.value = __('Reminder must be in the future')
    return
  }

  reminderError.value = ''
  saving.value = true

  try {
    // 1) أنشئ الكومنت وأمسك الاسم
    const ins = await call('frappe.client.insert', {
      doc: {
        doctype: 'Comment',
        reference_doctype: 'CRM Lead',
        reference_name: props.leadName,
        subject: commentTitle.value.trim() || null, // Add title if provided
        content,
        comment_type: 'Comment',
      },
    })
    const commentName = ins?.name || ins?.message?.name || null

    // 2) أضف الريمايندر مرتبط بالكومنت
    const descText = stripHtml(content)
    await call('crm.api.reminders.add_reminder', {
      doctype: 'CRM Lead',
      name: props.leadName,
      remind_at: toServerDatetime(reminderAtLocal.value),
      description: `Follow-up: "${descText.slice(0, 140)}${descText.length > 140 ? '…' : ''}"`,
      comment: commentName,
    })

    // 3) نظّف أعلام التأخير على كومنتات هذا المستخدم لهذا المستند
    try {
      await call('crm.api.reminders.clear_delayed_flags', {
        doctype: 'CRM Lead',
        name: props.leadName,
      })
    } catch (e) {
      // تجاهل لو الجدول/العمود غير موجود أو أي خطأ غير مؤثر
    }

    toast.success(__('FeedBack & reminder added'))
    newComment.value = ''
    commentTitle.value = '' // Clear title
    reminderAtLocal.value = '' // يرجع فاضي لإجبار اختيار جديد

    // أعِد التحميل
    await Promise.all([loadComments(), loadReminders()])
  } catch (e) {
    console.error('Error adding comment/reminder:', e)
    const errorMsg = e?.exc_type
      ? e?.message || __('Failed to add FeedBack/reminder')
      : e?.messages?.[0] || e?.message || __('Failed to add FeedBack/reminder')
    toast.error(errorMsg)
  } finally { saving.value = false }
}

onMounted(async () => {
  await refreshDelayedState()
  await Promise.all([loadComments(), loadReminders()])
})
</script>
