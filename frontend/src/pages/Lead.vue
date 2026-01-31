<template>
  <LayoutHeader v-if="lead.data">
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs">
        <template #prefix="{ item }">
          <Icon v-if="item.icon" :icon="item.icon" class="mr-2 h-4" />
        </template>
      </Breadcrumbs>
    </template>

    <template #right-header>
      <CustomActions v-if="lead.data._customActions?.length" :actions="lead.data._customActions" />
      <CustomActions v-if="document.actions?.length" :actions="document.actions" />

       <AssignTo v-model="assignees.data" doctype="CRM Lead" :docname="leadId" />


      <Dropdown
        v-if="document.doc"
        :options="filteredStatusOptions('lead', document.statuses?.length ? document.statuses : lead.data._customStatuses, triggerStatusChange)"

      >
        <template #default="{ open }">
          <Button :label="document.doc.status">
            <template #suffix><FeatherIcon :name="open ? 'chevron-up' : 'chevron-down'" class="h-4" /></template>
            <template #prefix>
              <IndicatorIcon :class="(getLeadStatus(document.doc.status) || {}).color || 'bg-gray-300'" />
            </template>
          </Button>
        </template>
      </Dropdown>

      <Button :label="__('Convert to Deal')" variant="solid" @click="showConvertToDealModal = true" />
      <Button :label="__('Reserve')" variant="solid" class="ml-2" @click="reserveFromLead" />
    </template>
  </LayoutHeader>

  <div v-if="lead?.data" class="flex">
    <Tabs as="div" v-model="tabIndex" :tabs="tabs">
      <template #tab-panel>
        <!-- ================= Payment Plans tab ================= -->
        <template v-if="isPaymentsTab">
          <div class="p-4 space-y-4">
            <div class="flex items-center justify-between">
              <div class="text-lg font-semibold">
                {{ __('Payment Plans') }}
                <span v-if="hydratedPlans.length" class="text-sm opacity-60">({{ hydratedPlans.length }})</span>
              </div>
              <Button variant="solid" @click="createPaymentPlan">
                <template #prefix><FeatherIcon name="plus" class="h-4" /></template>
                {{ __('New Payment Plan') }}
              </Button>
            </div>

            <div class="overflow-auto border rounded-lg">
              <table class="min-w-full text-sm">
                <thead class="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th class="px-4 py-2 text-left">{{ __('Plan Name') }}</th>
                    <th class="px-4 py-2 text-right">{{ __('Total Amount') }}</th>
                    <th class="px-4 py-2 text-left">{{ __('Modified') }}</th>
                    <th class="px-4 py-2 text-left">{{ __('Owner') }}</th>
                    <th class="px-4 py-2 text-center">{{ __('Actions') }}</th>
                  </tr>
                </thead>

                <tbody>
                  <tr v-if="!paymentPlans.loading && !hydratedPlans.length">
                    <td colspan="5" class="px-4 py-6 text-center text-gray-500">
                      {{ __('No payment plans yet.') }}
                    </td>
                  </tr>

                  <tr v-else-if="paymentPlans.loading">
                    <td colspan="5" class="px-4 py-6 text-sm text-gray-500">
                      {{ __('Loading…') }}
                    </td>
                  </tr>

                  <tr
                    v-for="p in hydratedPlans"
                    :key="p.name"
                    class="border-t hover:bg-gray-50/60 dark:hover:bg-gray-800/40 transition-colors"
                  >
                    <!-- PLAN NAME (strictly from plan_name/title; never show id unless both missing) -->
                    <td class="px-4 py-2">
                      <div class="font-medium truncate" :title="displayPlanName(p)">
                        <button class="underline-offset-2 hover:underline" @click="openPaymentPlan(p.name)">
                          {{ displayPlanName(p) }}
                        </button>
                      </div>
                      <!-- If you do NOT want to show the internal id at all, remove the block below -->
                      <div class="text-xs text-gray-500 flex items-center gap-2">
                        <span class="truncate">{{ p.name }}</span>
                        <button class="text-[11px] opacity-70 hover:opacity-100 underline" @click="copyToClipboard(p.name)">
                          {{ __('copy') }}
                        </button>
                      </div>
                    </td>

                    <!-- TOTAL -->
                    <td class="px-4 py-2 text-right">
                      <span v-if="p.__amount != null">{{ formatAmount(p.__amount, p.__currency) }}</span>
                      <span v-else>—</span>
                    </td>

                    <!-- MODIFIED -->
                    <td class="px-4 py-2">
                      <span v-if="p.__modified" :title="p.__modified">{{ prettyDate(p.__modified) }}</span>
                      <span v-else>—</span>
                    </td>

                    <!-- OWNER -->
                    <td class="px-4 py-2">
                      <span :title="p.__owner || ''">{{ ownerShort(p.__owner) || '—' }}</span>
                    </td>

                    <!-- ACTIONS -->
                    <td class="px-4 py-2 text-center whitespace-nowrap">
                      <Button size="sm" @click="openPaymentPlan(p.name)">
                        <template #prefix><FeatherIcon name="external-link" class="h-4" /></template>
                        {{ __('Open') }}
                      </Button>
                      <Button
                        size="sm"
                        variant="subtle"
                        theme="red"
                        class="ml-2"
                        @click="confirmDeletePaymentPlan(p.name)"
                      >
                        <template #prefix><FeatherIcon name="trash-2" class="h-4" /></template>
                        {{ __('Delete') }}
                      </Button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>

        <!-- ================= Information & Activity tab ================= -->
        <template v-else-if="isInformationTab">
          <LeadInformationAndFeedback
            :leadData="lead.data"
            :doctype="'CRM Lead'"
            :docname="lead.data?.name || props.leadId"
          />
        </template>

        <!-- ================= default tab ================= -->
        <template v-else>
          <Activities
            ref="activities"
            doctype="CRM Lead"
            :docname="lead.data?.name || props.leadId"
            :tabs="tabs"
            v-model:reload="reload"
            v-model:tabIndex="tabIndex"
            v-model="lead"
            @beforeSave="saveChanges"
            @afterSave="reloadAssignees"
          />
        </template>
      </template>
    </Tabs>

    <!-- ===== Right panel (unchanged) ===== -->
    <Resizer class="flex flex-col justify-between border-l" side="right">
      <div
        class="flex h-10.5 cursor-copy items-center border-b px-5 py-2.5 text-lg font-medium text-ink-gray-9"
        @click="copyToClipboard(lead.data.name)"
      >
        {{ __(lead.data.name) }}
      </div>

      <FileUploader @success="(file) => updateField('image', file.file_url)" :validateFile="validateIsImageFile">
        <template #default="{ openFileSelector, error: fileErr }">
          <div class="flex items-center justify-start gap-5 border-b p-5">
            <div class="group relative size-12">
              <Avatar size="3xl" class="size-12" :label="title" :image="lead.data.image" />
              <component
                :is="lead.data.image ? Dropdown : 'div'"
                v-bind="
                  lead.data.image
                    ? {
                        options: [
                          { icon: 'upload', label: lead.data.image ? __('Change image') : __('Upload image'), onClick: openFileSelector },
                          { icon: 'trash-2', label: __('Remove image'), onClick: () => updateField('image', '') },
                        ],
                      }
                    : { onClick: openFileSelector }
                "
                class="!absolute bottom-0 left-0 right-0"
              >
                <div
                  class="z-1 absolute bottom-0.5 left-0 right-0.5 flex h-9 cursor-pointer items-center justify-center rounded-b-full bg-black bg-opacity-40 pt-3 opacity-0 duration-300 ease-in-out group-hover:opacity-100"
                  style="-webkit-clip-path: inset(12px 0 0 0); clip-path: inset(12px 0 0 0);"
                >
                  <CameraIcon class="size-4 cursor-pointer text-white" />
                </div>
              </component>
            </div>

            <div class="flex flex-col gap-2.5 truncate">
              <Tooltip :text="lead.data.lead_name || __('Set first name')">
                <div class="truncate text-2xl font-medium text-ink-gray-9">{{ title }}</div>
              </Tooltip>

              <div class="flex gap-1.5">
                <Tooltip v-if="callEnabled" :text="__('Make a call')">
                  <div>
                    <Button
                      @click="() => lead.data.mobile_no ? makeCall(lead.data.mobile_no) : toast.error(__('No phone number set'))"
                    >
                      <template #icon><PhoneIcon /></template>
                    </Button>
                  </div>
                </Tooltip>

                <Tooltip :text="__('Send an email')">
                  <div>
                    <Button @click="lead.data.email ? openEmailBox() : toast.error(__('No email set'))">
                      <template #icon><Email2Icon /></template>
                    </Button>
                  </div>
                </Tooltip>

                <Tooltip :text="__('Go to website')">
                  <div>
                    <Button @click="lead.data.website ? openWebsite(lead.data.website) : toast.error(__('No website set'))">
                      <template #icon><LinkIcon /></template>
                    </Button>
                  </div>
                </Tooltip>

                <Tooltip :text="__('Attach a file')">
                  <div><Button @click="showFilesUploader = true"><template #icon><AttachmentIcon /></template></Button></div>
                </Tooltip>

                <Tooltip :text="__('Delete')">
                  <div><Button @click="deleteLeadWithModal(lead.data.name)" variant="subtle" theme="red" icon="trash-2" /></div>
                </Tooltip>
              </div>

              <div v-if="fileErr || error" class="text-red-600 text-sm">{{ fileErr || error }}</div>
            </div>
          </div>
        </template>
      </FileUploader>

      <SLASection v-if="lead.data.sla_status" v-model="lead.data" @updateField="updateField" />

      <div v-if="sections.data" class="flex flex-1 flex-col justify-between">
        <SidePanelLayout
          :sections="sections.data"
          doctype="CRM Lead"
          :docname="lead.data.name"
          @reload="sections.reload"
          @afterFieldChange="reloadAssignees"
        />
      </div>
    </Resizer>
  </div>

  <ErrorPage v-else-if="errorTitle" :errorTitle="errorTitle" :errorMessage="errorMessage" />

  <ConvertToDealModal v-if="showConvertToDealModal" v-model="showConvertToDealModal" :lead="lead.data" />

  <FilesUploader
    v-if="lead.data?.name"
    v-model="showFilesUploader"
    doctype="CRM Lead"
    :docname="lead.data.name"
    @after="() => { activities?.all_activities?.reload(); changeTabTo('attachments') }"
  />

  <DeleteLinkedDocModal v-if="showDeleteLinkedDocModal" v-model="showDeleteLinkedDocModal" :doctype="'CRM Lead'" :docname="props.leadId" name="Leads" />

  <!-- NEW: Reservation create modal (prefilled with this lead) -->
  <ReservationModal
    v-if="lead.data?.name"
    v-model="showReserveModal"
    mode="create"
    :seedLeadId="lead.data.name"
    :seedLeadLabel="title"
    @created="(r) => { toast.success(__('Reservation created')); router.push({ name: 'Reservations', query: { name: r?.name } }) }"
  />

</template>

<script setup>
import ReservationModal from '@/components/Modals/ReservationModal.vue'
import DeleteLinkedDocModal from '@/components/DeleteLinkedDocModal.vue'
import ErrorPage from '@/components/ErrorPage.vue'
import Icon from '@/components/Icon.vue'
import Resizer from '@/components/Resizer.vue'
import ActivityIcon from '@/components/Icons/ActivityIcon.vue'
import EmailIcon from '@/components/Icons/EmailIcon.vue'
import Email2Icon from '@/components/Icons/Email2Icon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import WhatsAppIcon from '@/components/Icons/WhatsAppIcon.vue'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import CameraIcon from '@/components/Icons/CameraIcon.vue'
import LinkIcon from '@/components/Icons/LinkIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import Activities from '@/components/Activities/Activities.vue'
import AssignTo from '@/components/AssignTo.vue'
import FilesUploader from '@/components/FilesUploader/FilesUploader.vue'
import SidePanelLayout from '@/components/SidePanelLayout.vue'
import SLASection from '@/components/SLASection.vue'
import CustomActions from '@/components/CustomActions.vue'
import ConvertToDealModal from '@/components/Modals/ConvertToDealModal.vue'
import LeadInformationAndFeedback from '@/components/LeadInformationAndFeedback.vue'

import { openWebsite, setupCustomizations, copyToClipboard, validateIsImageFile } from '@/utils'
import { getView } from '@/utils/view'
import { getSettings } from '@/stores/settings'
import { globalStore } from '@/stores/global'
import { statusesStore } from '@/stores/statuses'
import { getMeta } from '@/stores/meta'
import { useDocument } from '@/data/document'
import { whatsappEnabled, callEnabled } from '@/composables/settings'
import { createResource, FileUploader, Dropdown, Tooltip, Avatar, Tabs, Breadcrumbs, call, usePageMeta, toast } from 'frappe-ui'
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useActiveTabManager } from '@/composables/useActiveTabManager'

const PAYMENT_PLAN_DOCTYPE = 'Payment Plan'
const DEFAULT_PLAN_STATUS = 'Draft'
const DEFAULT_PLAN_YEARS = 1
const SYS_CURRENCY = window?.frappe?.boot?.sysdefaults?.currency || ''

const { brand } = getSettings()
const { $dialog, $socket, makeCall } = globalStore()
const { statusOptions, getLeadStatus } = statusesStore()
const filteredStatusOptions = (...args) => {
  const options = statusOptions(...args)
  const blocked = ['wrong number','Visiting','Reschedule meeting','Not Available','Qualified'] // customize as needed
  return options.filter(opt => !blocked.includes(opt.label || opt))
}
const { doctypeMeta } = getMeta('CRM Lead')

const route = useRoute()
const router = useRouter()

const props = defineProps({ leadId: { type: String, required: true } })

const errorTitle = ref('')
const errorMessage = ref('')
const error = ref('')
const showDeleteLinkedDocModal = ref(false)
const showConvertToDealModal = ref(false)
const showFilesUploader = ref(false)
const showReserveModal = ref(false)
const RESERVED_STATUS = 'Reserved'

const { triggerOnChange, assignees, document } = useDocument('CRM Lead', props.leadId)

async function triggerStatusChange(value) { await triggerOnChange('status', value); document.save.submit() }


/**
 * Set status to 'Reserved' and open the Reservation modal prefilled with this lead.
 */
async function reserveFromLead() {
  try {
    // 1) ensure status exists in dropdown choices (optional, safe no-op if already present)
    if (Array.isArray(document.statuses) && !document.statuses.includes(RESERVED_STATUS)) {
      document.statuses.push(RESERVED_STATUS)
    }
    // 2) update the lead status
    await triggerStatusChange(RESERVED_STATUS)
    // 3) open the reservation modal (prefill with this lead)
    showReserveModal.value = true
  } catch (e) {
    toast.error(e?.messages?.[0] || e?.message || __('Could not set status to Reserved'))
  }
}

const lead = createResource({
  url: 'frappe.client.get',
  params: { doctype: 'CRM Lead', name: props.leadId },
  cache: ['lead', props.leadId],
  onSuccess: (res) => {
    const doc = res?.message ?? res
    errorTitle.value = ''
    errorMessage.value = ''
    // make sure lead.data is the pure doc object
    lead.data = doc
    setupCustomizations(lead, {
      doc,
      $dialog,
      $socket,
      router,
      toast,
      updateField,
      createToast: toast.create,
      deleteDoc: deleteLead,
      resource: { lead, sections },
      call,
    })
  },
  onError: (err) => {
    // If the route param is wrong (e.g., a Reservation id), you’ll get DoesNotExistError here
    if (err.messages?.[0]) {
      errorTitle.value = __('Not permitted')
      errorMessage.value = __(err.messages?.[0])
    } else {
      router.push({ name: 'Leads' })
    }
  },
})

// ====== server-driven Activity visibility: request sales-role info ======
onMounted(async () => {
  // ensure lead fetch / payment plans behavior still happens
  if (!lead.data) lead.fetch()
  if (isPaymentsTab.value) refreshPaymentPlans()

  // call the server endpoint you created in apps/crm/crm/permissions.py
  try {
    const res = await call('crm.api.permissions.is_sales_user')
    // server may return boolean or string/number; normalize common cases
    if (res === true || res === 'true' || res === 1 || res === '1') {
      isSalesUserFlag.value = true
    } else if (res === false || res === 'false' || res === 0 || res === '0') {
      isSalesUserFlag.value = false
    } else {
      // unknown value — keep null to avoid flashing Activity for restricted users
      isSalesUserFlag.value = null
    }
  } catch (e) {
    // on error keep null (safer)
    isSalesUserFlag.value = null
    console && console.warn && console.warn('crm.permissions.is_sales_user failed', e)
  }
})

onMounted(() => {
  if (!lead.data) lead.fetch()
  if (isPaymentsTab.value) refreshPaymentPlans()
})

const reload = ref(false)
const activities = ref(null)

/* ---------------- Breadcrumbs & Title ---------------- */
const breadcrumbs = computed(() => {
  let items = [{ label: __('Leads'), route: { name: 'Leads' } }]
  if (route.query.view || route.query.viewType) {
    let view = getView(route.query.view, route.query.viewType, 'CRM Lead')
    if (view) items.push({ label: __(view.label), icon: view.icon, route: { name: 'Leads', params: { viewType: route.query.viewType }, query: { view: route.query.view } } })
  }
  items.push({ label: title.value, route: { name: 'Lead', params: { leadId: lead.data?.name || props.leadId } } })
  return items
})
const title = computed(() => { let t = doctypeMeta['CRM Lead']?.title_field || 'name'; return lead.data?.[t] || props.leadId })
usePageMeta(() => ({ title: title.value, icon: brand.favicon }))

/* ---------------- Tabs (server-driven Activity visibility) ---------------- */
// reactive flag set from server
const isSalesUserFlag = ref(null) // null = unknown while server call pending

// base tabs (Activity injected later if allowed)
const baseTabOptions = [
  { name: 'Information & Activity', label: __('Information & Activity'), icon: DetailsIcon },
  { name: 'Payment Plans', label: __('Payment Plans'), icon: DetailsIcon },
  { name: 'Tasks', label: __('Tasks'), icon: TaskIcon },
  { name: 'Notes', label: __('Notes'), icon: NoteIcon },
  { name: 'Attachments', label: __('Attachments'), icon: AttachmentIcon },
  // WhatsApp remains conditional on feature flag
  { name: 'WhatsApp', label: __('WhatsApp'), icon: WhatsAppIcon, condition: () => whatsappEnabled.value },
]

// tabs computed uses server flag to decide Activity visibility
const tabs = computed(() => {
  const t = baseTabOptions.slice()

  // showActivity: only when we explicitly know user is NOT sales (false)
  // initial null => hide (avoids flashing Activity before server responds)
  const showActivity = (isSalesUserFlag.value === null) ? false : (!isSalesUserFlag.value)

  if (showActivity) {
    // insert Activity just before WhatsApp (index 6 keeps ordering after Attachments)
    t.splice(6, 0, { name: 'Activity', label: __('Activity'), icon: ActivityIcon })
  }

  return t.filter((tab) => (tab.condition ? tab.condition() : true))
})

const isPaymentsTab = computed(() => { try { return tabs.value?.[tabIndex.value]?.name === 'Payment Plans' } catch { return false } })
// Check if we're in the Information & Activity tab
const isInformationTab = computed(() => { try { return tabs.value?.[tabIndex.value]?.name === 'Information & Activity' } catch { return false } })

// --- hide Activity tab for Sales User on portal ---
const isSalesUser = computed(() => {
  try {
    // try multiple places where roles may live on portal pages
    const a = window?.frappe?.session?.user_roles;
    const b = window?.frappe?.boot?.user_roles;
    const c = window?.frappe?.boot?.user?.roles;
    const roles = Array.isArray(a) ? a : Array.isArray(b) ? b : Array.isArray(c) ? c : [];
    // accept common name variants just in case
    const salesNames = ['Sales User', 'Sales', 'Salesman', 'Salesperson'];
    return roles.some(r => salesNames.includes(r));
  } catch (e) { return false; }
});

const { tabIndex, changeTabTo } = useActiveTabManager(tabs, 'lastLeadTab')
watch(tabs, (value) => {
  if (value && route.params.tabName) {
    let index = value.findIndex((tab) => tab.name.toLowerCase() === route.params.tabName.toLowerCase())
    if (index !== -1) tabIndex.value = index
  }
})
watch([isPaymentsTab, () => lead.data?.name], ([isPayTab]) => { if (isPayTab) refreshPaymentPlans() })

/* ---------------- Fields sections ---------------- */
const sections = createResource({
  url: 'crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
  cache: ['sidePanelSections', 'CRM Lead'],
  params: { doctype: 'CRM Lead' },
  auto: true,
})

/* ---------------- Payment Plans data & hydration ---------------- */
const paymentPlans = createResource({
  url: 'frappe.client.get_list',
  params: {
    doctype: PAYMENT_PLAN_DOCTYPE,
    // only fetch minimal fields; we'll hydrate each row to get totals/currency/etc.
    fields: ['name','plan_name','title','lead','modified','owner'],
    filters: [['lead', '=', props.leadId]],
    order_by: 'modified desc',
    limit_page_length: 50,
  },
  auto: false,
  onSuccess: hydratePlans,
})

const hydratedPlans = ref([])

async function hydratePlans(list = paymentPlans.data || []) {
  if (!Array.isArray(list) || !list.length) { hydratedPlans.value = []; return }
  const chunk = 8
  const out = []
  for (let i = 0; i < list.length; i += chunk) {
    const slice = list.slice(i, i + chunk)
    const reqs = slice.map(r =>
      call('frappe.client.get', {
        doctype: PAYMENT_PLAN_DOCTYPE,
        name: r.name,
      }).then((res) => res?.message ?? res).catch(() => null)
    )
    const docs = await Promise.all(reqs)
    for (let j = 0; j < slice.length; j++) {
      const row = slice[j]
      const doc = docs[j] || {}

      // derive total (stored or sum of schedule)
      let total = Number(doc.total_price ?? doc.total_amount)
      if (!Number.isFinite(total) || total === 0) {
        if (Array.isArray(doc.schedule)) {
          total = doc.schedule.reduce((s, it) => s + Number(it.amount || 0), 0)
        } else {
          total = null
        }
      }

      out.push({
        ...row,
        // no status anymore
        __label: derivePlanLabel(doc),
        __amount: Number.isFinite(total) ? total : null,
        __currency: doc.currency || SYS_CURRENCY || '',
        __modified: doc.modified || row.modified || doc.creation || '',
        __owner: doc.owner || row.owner || '',
      })
    }
  }
  hydratedPlans.value = out
}

function refreshPaymentPlans() {
  if (!lead.data?.name) return
  hydratedPlans.value = []
  paymentPlans.reload({
    doctype: PAYMENT_PLAN_DOCTYPE,
    filters: [['lead', '=', lead.data.name]],
  })
}

function derivePlanLabel(doc = {}) {
  const fields = ['plan_name', 'title', 'unit_name', 'project_name', 'name']
  for (const f of fields) {
    const v = (doc[f] ?? '').toString().trim()
    if (v) return f === 'name' ? '' : v // never *display* the id
  }
  return ''
}

function openPaymentPlan(planName) {
  try { router.push({ name: 'PaymentPlan', query: { plan: planName } }) }
  catch { window.open(`/app/payment-plan/${encodeURIComponent(planName)}`, '_blank') }
}

async function deletePaymentPlan(name) {
  try {
    await call('frappe.client.delete', { doctype: PAYMENT_PLAN_DOCTYPE, name })
    toast.success(__('Payment Plan deleted'))
    refreshPaymentPlans()
  } catch (e) {
    toast.error(e?.messages?.[0] || e?.message || __('Could not delete Payment Plan'))
  }
}
function confirmDeletePaymentPlan(name) {
  // robust confirm (no dependency on injected $dialog)
  const ok = window.confirm(__('Delete this Payment Plan?'))
  if (ok) deletePaymentPlan(name)
}

async function createPaymentPlan() {
  try {
    const planTitle = `${__('Payment Plan for')} ${titleRef.value || lead.data?.name || ''}`.trim()
    const payload = {
      doctype: PAYMENT_PLAN_DOCTYPE,
      title: planTitle,
      plan_name: planTitle, // ensure plan_name is set so the list shows a proper name
      lead: lead.data?.name,
      status: DEFAULT_PLAN_STATUS,
      years: DEFAULT_PLAN_YEARS,
    }
    const res = await call('frappe.client.insert', { doc: payload })
    toast.success(__('Payment Plan created'))
    openPaymentPlan(res?.name)
    refreshPaymentPlans()
  } catch (e) {
    const msg = e?.messages?.[0] || e?.message || ''
    toast.error(msg && msg.toLowerCase().includes('mandatory') ? msg : __('Could not create Payment Plan'))
  }
}

const titleRef = computed(() => {
  const t = doctypeMeta['CRM Lead']?.title_field || 'name'
  return lead.data?.[t]
})

/* -------- Small UI helpers -------- */
function displayPlanName(p) { return p?.__label || p?.plan_name || p?.title || '—' }
function formatAmount(n, cur) { const s = Number(n).toLocaleString(); return cur ? `${s} ${cur}` : s }
function prettyDate(iso) { try { return window.frappe.datetime.prettyDate(iso) } catch { return iso } }
function ownerShort(email) { if (!email) return ''; const at = String(email).indexOf('@'); return at > 0 ? email.slice(0, at) : email }

/* ---------------- AssignTo visibility ---------------- */


/* ---------------- Common helpers ---------------- */
function updateField(name, value, callback) {
  updateLead(name, value, () => { if (lead.data) lead.data[name] = value; callback?.() })
}
function updateLead(fieldname, value, callback) {
  value = Array.isArray(fieldname) ? '' : value
  if (!Array.isArray(fieldname) && validateRequired(fieldname, value)) return

  createResource({
    url: 'frappe.client.set_value',
    params: { doctype: 'CRM Lead', name: props.leadId, fieldname, value },
    auto: true,
    onSuccess: () => { lead.reload(); reload.value = true; toast.success(__('Lead updated successfully')); callback?.() },
    onError: (err) => { toast.error(err.messages?.[0] || __('Error updating lead')) },
  })
}
function validateRequired(fieldname, value) {
  let meta = lead.data?.fields_meta || {}
  if (meta?.[fieldname]?.reqd && !value) { toast.error(__('{0} is a required field', [meta[fieldname].label])); return true }
  return false
}
async function deleteLead(name) { await call('frappe.client.delete', { doctype: 'CRM Lead', name }); router.push({ name: 'Leads' }) }
async function deleteLeadWithModal(name) { showDeleteLinkedDocModal.value = true }
function openEmailBox() {
  let currentTab = tabs.value[tabIndex.value]
  if (!['Emails', 'Comments', 'Activity'].includes(currentTab.name)) activities.value.changeTabTo('emails')
  nextTick(() => (activities.value.emailBox.show = true))
}
function saveChanges(data) {
  document.save.submit(null, {
    onSuccess: () => reloadAssignees(data),
  })
}

function reloadAssignees(data) {
  if (data?.hasOwnProperty('lead_owner')) {
    assignees.reload()
  }
}
</script>

<style scoped>
table thead th { font-weight: 600; }
.rounded-lg { border-radius: 0.75rem; }
</style>
