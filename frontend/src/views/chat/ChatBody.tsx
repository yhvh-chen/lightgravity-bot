import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'

import {
  createAttachmentsApi,
  newPrivateAttachmentId,
  supportsPrivateAttachments,
  type AttachmentsApi,
} from '../../api/attachments'
import { getRuntimeToken } from '../../api/auth'
import { chatApi, type ChatApi, type ResolvedSourceBindingsData } from '../../api/chat'
import { fetchHealth } from '../../api/client'
import {
  supportsMaterialIntakeV2,
  supportsMediaDirectEmbedding,
} from '../../api/backendCompatibility'
import {
  createSourcesApi,
  type SourcesApi,
  type SourcesRuntimeConfig,
} from '../../api/sources'
import {
  isPrivateAttachment,
  MESSAGE_SOURCE_REFS_MAX,
  type Attachment,
  type HealthResponse,
  type SourceRefInput,
} from '../../api/types'
import { useShell } from '../../app/ShellProvider'
import { useAuth } from '../../app/AuthProvider'
import { draftKey, type ChatChannel } from '../../app/uiState'
import { ChatComposer } from '../../components/ChatComposer'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { Icon } from '../../components/icons'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { StatusBadge } from '../../components/StatusBadge'
import {
  ChatDraftChips,
  ChatMaterialIntake,
  ChatMaterialReceipts,
} from './ChatMaterialIntake'
import { ChatSourcePicker } from './ChatSourcePicker'
import { ChatSources } from './ChatSources'
import { useChat } from './useChat'
import { useChatDrafts, useChatMaterials } from './useChatMaterials'
import { useChatSelection } from './useChatSelection'

export interface ChatBodyProps {
  /** `main` = Chat view body; `rail` = right column on other views. */
  variant: 'main' | 'rail'
  onRequestClose?: () => void
  /** Injectable for tests; defaults to the real `/conversations|/tasks` endpoints. */
  api?: ChatApi
  /** Injectable sources client; defaults to the real `/sources|/search` endpoints. */
  sourcesApi?: SourcesApi
  /** Runtime token source for protected material writes. */
  sourcesRuntime?: SourcesRuntimeConfig
  /** Injectable private-attachment client for tests; defaults to the real routes. */
  attachmentsApi?: AttachmentsApi
}

interface PendingAttachment {
  path: string
  media_type: string | null
}

interface PrivatePendingAttachment {
  attachmentId: string
  filename: string
  mediaType: string
  size: number
  file: File
  status: 'uploading' | 'ready' | 'failed'
  error: string | null
}

/**
 * The single Chat surface (LG-013; docs/05 §3, design.md §2).
 *
 * The Chat view body and the shell's right rail render this same component, so
 * exactly one conversation is ever shown and no second session is created. It
 * reads the real global/Task message history, sends through the frozen
 * endpoints (keeping the draft on failure), and links a delivery reply to its
 * newly created Task so the caller can open the real Board state.
 */
export function ChatBody({
  variant,
  onRequestClose,
  api,
  sourcesApi,
  sourcesRuntime,
  attachmentsApi,
}: ChatBodyProps) {
  const { state, dispatch } = useShell()
  const { isTeam, requireLogin, personalChatAvailable } = useAuth()
  const taskRef = state.taskRef
  // LG-054: single-user mode has no team, so the only channel is the legacy
  // personal/global one.  In team mode the user picks; the default is Team.
  const channel: ChatChannel = isTeam ? (state.chatChannel === 'personal' && personalChatAvailable ? 'personal' : 'team') : 'personal'
  const privatePersonal = isTeam && channel === 'personal'
  // A private Personal conversation never carries Task scope; Team tasks stay
  // shared Team conversations.
  const effectiveTaskRef = privatePersonal ? null : taskRef
  const scope = { taskRef: effectiveTaskRef, personal: privatePersonal }
  // LG-142 seam adapter: useChat is a shared hook and stays read-only for this
  // package. The wrapper appends the send-time receipt refs to the exact same
  // wire request without changing useChat's idempotency or retry behavior.
  const sendSourceRefs = useRef<SourceRefInput[] | null>(null)
  const submitPending = useRef(false)
  const chat = useChat(
    scope,
    useMemo(() => {
      const base = api ?? chatApi
      return {
        ...base,
        sendMessage: (sendScope, body, signal) => {
          const refs = sendSourceRefs.current
          const nextBody = refs && refs.length > 0 ? { ...body, source_refs: refs } : body
          // Keep the injected-client call shape byte-identical for legacy rows.
          return signal
            ? base.sendMessage(sendScope, nextBody, signal)
            : base.sendMessage(sendScope, nextBody)
        },
      }
    }, [api]),
    // Team mode polls the active global/private conversation; single-user mode
    // passes no interval so the existing behavior is byte-for-byte unchanged.
    isTeam ? { pollIntervalMs: 3000, onUnauthorized: requireLogin } : {},
  )
  const resolvedSourcesApi = useMemo(
    () => sourcesApi ?? createSourcesApi(sourcesRuntime ?? { getApiToken: getRuntimeToken }),
    [sourcesApi, sourcesRuntime],
  )
  const materials = useChatMaterials(resolvedSourcesApi)
  const drafts = useChatDrafts(resolvedSourcesApi, { intakeMode: 'deferred' })
  const resolvedAttachmentsApi = useMemo(
    () =>
      attachmentsApi ??
      createAttachmentsApi({ getApiToken: getRuntimeToken }),
    [attachmentsApi],
  )
  const selection = useChatSelection(effectiveTaskRef)
  const [extrasOpen, setExtrasOpen] = useState(false)
  const [materialNotice, setMaterialNotice] = useState<string | null>(null)
  // Capability gate: default false so a 1.18 backend (or a failed health read)
  // never activates deferred intake/receipt v2. The real health response is
  // cached and re-checked before a file pick, closing the startup race.
  const [sharedIntakeV2, setSharedIntakeV2] = useState(false)
  const [mediaDirectEmbedding, setMediaDirectEmbedding] = useState(false)
  const [intakeCapabilityChecked, setIntakeCapabilityChecked] = useState(false)
  const healthRequest = useRef<Promise<HealthResponse> | null>(null)
  // Resolved source bindings for the most recent send in this scope, so the
  // freshly returned reply can show its Sources before/without a reload.
  const [lastSendSources, setLastSendSources] = useState<ResolvedSourceBindingsData | null>(null)
  const key = draftKey(effectiveTaskRef, isTeam ? channel : null)
  const draft = state.drafts[key] ?? ''
  const activeConversation = useRef(key)
  const conversationGeneration = useRef(0)
  if (activeConversation.current !== key) {
    activeConversation.current = key
    conversationGeneration.current += 1
  }
  const loadHealth = useCallback(() => {
    if (!healthRequest.current) {
      healthRequest.current = fetchHealth().catch((cause: unknown) => {
        healthRequest.current = null
        throw cause
      })
    }
    return healthRequest.current
  }, [])

  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      privateUploads.current.forEach((controller) => controller.abort())
      privateUploads.current.clear()
    }
  }, [])

  useEffect(() => {
    let active = true
    loadHealth()
      .then((health) => {
        if (!active) return
        setSharedIntakeV2(supportsMaterialIntakeV2(health))
        setMediaDirectEmbedding(supportsMediaDirectEmbedding(health))
        setIntakeCapabilityChecked(true)
      })
      .catch(() => {
        if (!active) return
        setSharedIntakeV2(false)
        setMediaDirectEmbedding(false)
        setIntakeCapabilityChecked(true)
      })
    return () => { active = false }
  }, [loadHealth])
  const [notice, setNotice] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [privateAttachments, setPrivateAttachments] = useState<PrivatePendingAttachment[]>([])
  const [privateAttachmentsAvailable, setPrivateAttachmentsAvailable] = useState<boolean | null>(null)
  const privateUploads = useRef<Map<string, AbortController>>(new Map())
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [hasNewMessages, setHasNewMessages] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const prevCountRef = useRef(0)

  // Scope change (including Task/channel switch) drops any transient reply
  // Sources so it can never leak across conversation boundaries (docs/10 §1).
  useEffect(() => {
    setLastSendSources(null)
    selection.clear()
    setAttachments([])
    // In-flight private uploads are aborted and their ids dropped so a late
    // response can never bind to the newly selected channel/account.
    privateUploads.current.forEach((controller) => controller.abort())
    privateUploads.current.clear()
    setPrivateAttachments([])
    setAttachmentError(null)
    materials.reset()
    drafts.reset()
    setExtrasOpen(false)
    // A scope switch starts at the latest message, not a stale "new messages"
    // badge held over from the previous conversation.
    atBottomRef.current = true
    prevCountRef.current = 0
    setHasNewMessages(false)
  }, [effectiveTaskRef, privatePersonal])

  useEffect(() => { setNotice(null) }, [privatePersonal])

  // Capability check (not a 404 probe): private uploads are disabled with an
  // honest explanation when the backend does not advertise the feature.
  useEffect(() => {
    if (!privatePersonal) {
      setPrivateAttachmentsAvailable(null)
      return
    }
    let active = true
    fetchHealth()
      .then((health) => {
        if (active) setPrivateAttachmentsAvailable(supportsPrivateAttachments(health))
      })
      .catch(() => {
        if (active) setPrivateAttachmentsAvailable(false)
      })
    return () => { active = false }
  }, [privatePersonal])

  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const grew = chat.messages.length > prevCountRef.current
    prevCountRef.current = chat.messages.length
    if (!grew) return
    // Never yank the viewport while the user is reading history: only auto-scroll
    // when already near the bottom, otherwise offer a "new messages" entry
    // (design.md §5). Incremental polling must not disturb the draft or scroll.
    if (atBottomRef.current) {
      list.scrollTop = list.scrollHeight
      setHasNewMessages(false)
    } else {
      setHasNewMessages(true)
    }
  }, [chat.messages.length])

  const handleScroll = () => {
    const list = listRef.current
    if (!list) return
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight <= 48
    atBottomRef.current = atBottom
    if (atBottom) setHasNewMessages(false)
  }

  const scrollToBottom = () => {
    const list = listRef.current
    if (!list) return
    list.scrollTop = list.scrollHeight
    atBottomRef.current = true
    setHasNewMessages(false)
  }

  const authorLabel = (message: (typeof chat.messages)[number]): string => {
    if (!isTeam) return message.role === 'user' ? 'You' : message.role
    // Team mode: the server writes the real author; legacy rows without one are
    // shown as Unknown rather than inventing a speaker (LG-050 §5).
    if (message.role === 'user') return message.author?.username ?? 'Unknown'
    if (message.role === 'assistant') return message.author?.username ?? 'Bot'
    return message.author?.username ?? message.role
  }

  const scopeLabel = effectiveTaskRef ?? (privatePersonal ? 'Personal' : 'Global')

  const switchToTeam = () => {
    setNotice(null)
    dispatch({ type: 'setChatChannel', channel: 'team' })
  }
  const switchToPersonal = () => {
    if (!isTeam || !personalChatAvailable) return
    // Privacy: leaving Team for Personal drops any Task scope so a shared task
    // context is never carried into the private conversation.
    setNotice(null)
    dispatch({ type: 'setChatChannel', channel: 'personal' })
    dispatch({ type: 'selectTask', taskRef: null })
  }

  const openSourceInFiles = (sourceId: string) => {
    // Meaningful backlink: open the real material in Files, keep the Task scope.
    dispatch({ type: 'selectItem', itemRef: `source:${sourceId}` })
    dispatch({ type: 'setView', view: 'files' })
  }

  const handleAddAttachment = (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value.trim()
    if (!value) return
    setAttachments((current) => [
      ...current,
      { path: value, media_type: guessMediaType(value) },
    ])
    setAttachmentError(null)
    event.target.value = ''
  }

  const uploadPrivateFile = (
    file: File,
    existing?: PrivatePendingAttachment,
  ) => {
    const attachmentId = existing?.attachmentId ?? newPrivateAttachmentId()
    privateUploads.current.get(attachmentId)?.abort()
    const controller = new AbortController()
    privateUploads.current.set(attachmentId, controller)
    const requestGeneration = conversationGeneration.current
    setPrivateAttachments((current) => {
      if (existing) {
        return current.map((item) =>
          item.attachmentId === attachmentId
            ? { ...item, file, filename: file.name, mediaType: file.type, size: file.size, status: 'uploading', error: null }
            : item,
        )
      }
      return [
        ...current,
        {
          attachmentId,
          filename: file.name,
          mediaType: file.type || 'application/octet-stream',
          size: file.size,
          file,
          status: 'uploading',
          error: null,
        },
      ]
    })
    void resolvedAttachmentsApi
      .upload(file, { attachmentId, signal: controller.signal })
      .then((uploaded) => {
        if (!mounted.current || requestGeneration !== conversationGeneration.current) return
        setPrivateAttachments((current) =>
          current.map((item) =>
            item.attachmentId === attachmentId
              ? {
                  ...item,
                  filename: uploaded.filename,
                  mediaType: uploaded.media_type ?? item.mediaType,
                  size: uploaded.size,
                  status: 'ready',
                  error: null,
                }
              : item,
          ),
        )
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        if (!mounted.current || requestGeneration !== conversationGeneration.current) return
        const message = cause instanceof Error ? cause.message : 'Upload failed'
        setPrivateAttachments((current) =>
          current.map((item) =>
            item.attachmentId === attachmentId
              ? { ...item, status: 'failed', error: message }
              : item,
          ),
        )
      })
      .finally(() => {
        if (privateUploads.current.get(attachmentId) === controller) {
          privateUploads.current.delete(attachmentId)
        }
      })
  }

  const handleFilesPicked = async (files: File[]) => {
    if (files.length === 0) return
    setAttachmentError(null)
    if (privatePersonal) {
      if (privateAttachmentsAvailable !== true) {
        setAttachmentError(
          'Private attachments are unavailable on this backend (private_attachments capability missing).',
        )
        return
      }
      const remaining = 3 - privateAttachments.length
      if (remaining <= 0) {
        setAttachmentError('At most 3 private attachments are allowed per message.')
        return
      }
      if (files.length > remaining) {
        setAttachmentError(`Only ${remaining} more private attachment(s) can be added.`)
      }
      files.slice(0, remaining).forEach((file) => uploadPrivateFile(file))
      return
    }

    // Shared Team/single-user intake: check the real capability before choosing
    // the path. A 1.18 backend keeps its existing pre-send upload behavior and
    // never sees `intake_mode`/`source_refs`; a 1.19 backend gets local drafts.
    const requestGeneration = conversationGeneration.current
    let intakeV2 = sharedIntakeV2
    try {
      const health = await loadHealth()
      intakeV2 = supportsMaterialIntakeV2(health)
      if (mounted.current) {
        setSharedIntakeV2(intakeV2)
        setMediaDirectEmbedding(supportsMediaDirectEmbedding(health))
        setIntakeCapabilityChecked(true)
      }
    } catch {
      intakeV2 = false
      if (mounted.current) setIntakeCapabilityChecked(true)
    }
    if (!mounted.current || requestGeneration !== conversationGeneration.current) return
    if (intakeV2) {
      const result = drafts.addFiles(files)
      if (result.rejected > 0) {
        setAttachmentError(
          `At most ${MESSAGE_SOURCE_REFS_MAX} files can be attached to one message.`,
        )
      }
      return
    }
    // Legacy 1.18 path (unchanged): no source_refs are sent.
    void materials.uploadFiles(files, { taskRef: effectiveTaskRef })
  }

  const removePrivateAttachment = (attachment: PrivatePendingAttachment) => {
    privateUploads.current.get(attachment.attachmentId)?.abort()
    privateUploads.current.delete(attachment.attachmentId)
    setPrivateAttachments((current) =>
      current.filter((item) => item.attachmentId !== attachment.attachmentId),
    )
    if (attachment.status === 'ready') {
      // Best-effort cleanup of an unsent upload; never block the composer.
      void resolvedAttachmentsApi.remove(attachment.attachmentId).catch(() => undefined)
    }
  }

  const retryPrivateAttachment = (attachment: PrivatePendingAttachment) => {
    uploadPrivateFile(attachment.file, attachment)
  }

  const submitDraft = async () => {
    const attachmentOnly =
      !draft.trim() && !privatePersonal && sharedIntakeV2 && drafts.drafts.length > 0
    if (!draft.trim() && !attachmentOnly) return
    // The existing message API/hook require content. This fixed receipt caption
    // contains no file names, delivery instructions, or implicit selected context.
    const content = attachmentOnly ? 'Attached materials.' : draft
    if (privatePersonal && privateAttachments.some((item) => item.status === 'uploading')) {
      setNotice('Wait for the attachment upload to finish before sending.')
      return
    }
    const requestGeneration = conversationGeneration.current
    const frozenTaskRef = effectiveTaskRef
    const frozenPersonal = privatePersonal
    const frozenDraftKey = key
    const frozenSelection = privatePersonal ? undefined : selection.requestRefs

    // Freeze intake to the scope that was active when Send was pressed. Each
    // not-yet-accepted draft is submitted once with deferred mode; accepted
    // sources already obtained by a failed message send are reused below.
    let sourceRefs: SourceRefInput[] | undefined
    if (!frozenPersonal && sharedIntakeV2 && drafts.drafts.length > 0) {
      try {
        sourceRefs = await drafts.intakeAll({ taskRef: frozenTaskRef })
      } catch (cause) {
        if (!mounted.current || requestGeneration !== conversationGeneration.current) return
        setNotice(
          `Not sent — ${cause instanceof Error ? cause.message : 'material intake failed'}. ` +
            'The draft and any accepted materials are kept; remove a failed file to continue.',
        )
        return
      }
      if (!mounted.current || requestGeneration !== conversationGeneration.current) return
    }

    const payload: Attachment[] = frozenPersonal
      ? privateAttachments
          .filter((item) => item.status === 'ready')
          .map((item) => ({ attachment_id: item.attachmentId }))
      : attachments.map((item) => ({
          path: item.path,
          media_type: item.media_type,
        }))
    const selectedRefs = frozenSelection
    setNotice(null)
    sendSourceRefs.current = sourceRefs ?? null
    try {
      const outcome = await chat.send(content, payload, selectedRefs)
      if (!mounted.current) return
      dispatch({ type: 'setDraft', key: frozenDraftKey, value: '' })
      if (requestGeneration !== conversationGeneration.current) return
      setAttachments([])
      setPrivateAttachments([])
      if (!frozenPersonal && sharedIntakeV2) drafts.clear()
      // Implementation choice (docs/10 §8): clear the selection once the rule
      // backend accepts the send, because the refs are now bound to that
      // message; a failed send keeps them so an explicit retry reuses them.
      if (selectedRefs && selectedRefs.length > 0) selection.clear()
      setLastSendSources(outcome.resolvedSources)
      if (outcome.kind === 'recorded') {
        // Team-mode plain message: persisted for the team only, no bot reply.
        setNotice('Shared with the team.')
      } else if (outcome.kind === 'switch_to_team') {
        setNotice('Personal is private and chat-only. Switch to Team to create a task or run delivery — nothing was created.')
      } else if (outcome.kind === 'unavailable') {
        setNotice('Personal chat needs a configured model. Configure one in Settings, or use Team.')
      } else if (outcome.kind === 'create_task' && outcome.createdTaskRef) {
        setNotice(`Created Task ${outcome.createdTaskRef}. Opening its Board scope.`)
        dispatch({ type: 'selectTask', taskRef: outcome.createdTaskRef })
      } else if (outcome.reply) {
        setNotice(null)
      }
    } catch {
      // A response for a departed channel must not change the active composer.
      if (!mounted.current || requestGeneration !== conversationGeneration.current) return
      setNotice('Not sent — see the error below. Your draft and attachments are kept.')
    } finally {
      sendSourceRefs.current = null
    }
  }

  const handleSubmit = async () => {
    // Enter/click can arrive twice before React paints the pending state.
    if (submitPending.current) return
    submitPending.current = true
    try {
      await submitDraft()
    } finally {
      submitPending.current = false
    }
  }

  return (
    <section
      className={`lg-chat lg-chat--${variant}`}
      aria-label={variant === 'main' ? 'Chat workspace' : 'Chat panel'}
    >
      <div className="lg-chat__channels">
        <div className="lg-chat__channels-row">
          <div className="lg-chat__channels-tabs" role="tablist" aria-label="Conversation channel">
            <button
              type="button"
              role="tab"
              aria-selected={channel === 'personal'}
              disabled={isTeam && !personalChatAvailable}
              title={isTeam && !personalChatAvailable ? 'Personal requires backend contract >= 1.14 and the personal_chat capability' : undefined}
              className={`lg-button${channel === 'personal' ? ' lg-button--primary' : ''}`}
              onClick={switchToPersonal}
            >
              Personal
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={channel === 'team'}
              disabled={!isTeam}
              title={!isTeam ? 'Enable team mode on the backend to use the shared team conversation' : undefined}
              className={`lg-button${channel === 'team' ? ' lg-button--primary' : ''}`}
              onClick={switchToTeam}
            >
              Team
            </button>
          </div>
          {onRequestClose ? (
            <button
              type="button"
              className="lg-icon-button"
              onClick={onRequestClose}
              aria-label="Close chat panel"
            >
              <Icon name="close" />
            </button>
          ) : null}
        </div>
        {isTeam && !personalChatAvailable ? (
          <p className="lg-chat__channel-note">
            Personal is unavailable on this backend. Update to contract 1.14 or later with
            personal_chat enabled; shared Team conversations remain available.
          </p>
        ) : !isTeam ? (
          <p className="lg-chat__channel-note">
            Team mode is not enabled on this backend; enable team mode to use the shared team
            conversation.
          </p>
        ) : null}
      </div>

      {effectiveTaskRef ? (
        <div className="lg-chat__header lg-chat__header--task">
          <span className="lg-chat__subtitle">
            Task {effectiveTaskRef}
            <button
              type="button"
              className="lg-link-button"
              onClick={() => dispatch({ type: 'selectTask', taskRef: null })}
            >
              {isTeam ? 'Team conversation' : 'Conversation'}
            </button>
          </span>
        </div>
      ) : null}

      <div
        className="lg-chat__messages"
        aria-label="Conversation messages"
        ref={listRef}
        onScroll={handleScroll}
      >
        {chat.error ? (
          <ErrorState
            title={chat.error.httpStatus === 404
              ? effectiveTaskRef ? 'Task conversation unavailable' : 'Conversation service unavailable'
              : 'Could not load messages'}
            message={chat.error.message}
            code={chat.error.code}
            retryable={chat.error.retryable}
            requestId={chat.error.requestId}
            onRetry={chat.refresh}
          />
        ) : null}
        {chat.error?.httpStatus === 404 ? (
          <div className="lg-chat__recovery">
            <p>Your draft is kept. {effectiveTaskRef ? 'The task or conversation endpoint may no longer be available.' : 'Check that the server supports conversations.'}</p>
            <button type="button" className="lg-button" onClick={() => dispatch({ type: 'setView', view: 'files' })}>Choose task in Files</button>
            {effectiveTaskRef ? <button type="button" className="lg-button" onClick={() => dispatch({ type: 'selectTask', taskRef: null })}>Return to conversation</button> : null}
          </div>
        ) : null}
        {!chat.error && chat.loading ? (
          <EmptyState title="Loading conversation…">Reading {scopeLabel} history.</EmptyState>
        ) : null}
        {chat.messages.map((message) => (
          <article
            key={message.message_id}
            className={`lg-message lg-message--${message.role === 'user' ? 'user' : 'assistant'}`}
          >
            <div className="lg-message__meta">
              <span>{authorLabel(message)}</span>
              {message.at ? <span>{message.at}</span> : null}
              {message.resource_result?.status ? (
                <StatusBadge kind="neutral">
                  resource: {message.resource_result.status}
                </StatusBadge>
              ) : null}
            </div>
            <div className="lg-message__bubble">
              <MarkdownViewer content={message.content} />
            </div>
            {message.attachments.length > 0 ? (
              <ul className="lg-chat__attachments" aria-label="Attachments">
                {message.attachments.map((attachment, index) => (
                  <li
                    key={
                      isPrivateAttachment(attachment)
                        ? attachment.attachment_id
                        : `${attachment.path}-${index}`
                    }
                  >
                    <Icon name="files" size={14} />
                    <span className="lg-card__path">
                      {isPrivateAttachment(attachment)
                        ? attachment.filename ?? attachment.attachment_id
                        : attachment.path}
                    </span>
                    {isPrivateAttachment(attachment) && attachment.context_status ? (
                      <span className="lg-chat__attachment-status">
                        {privateContextLabel(attachment.context_status)}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {/* Persisted reply bindings (legacy rows have no `data` ⇒ nothing). */}
            <ChatSources data={message.data} onOpen={openSourceInFiles} />
            {/* Receipt-only refs stay separate from selected context. */}
            {sharedIntakeV2 && message.source_refs && message.source_refs.length > 0 ? (
              <ChatMaterialReceipts
                refs={message.source_refs}
                api={resolvedSourcesApi}
                onOpen={openSourceInFiles}
                materialIntakeV2={sharedIntakeV2}
                mediaDirectEmbedding={mediaDirectEmbedding}
              />
            ) : null}
          </article>
        ))}
      </div>

      <footer className="lg-chat__footer">
        {hasNewMessages ? (
          <button
            type="button"
            className="lg-button lg-chat__new-messages"
            onClick={scrollToBottom}
          >
            New messages ↓
          </button>
        ) : null}
        {notice ? (
          <p className="lg-notice" role="status">
            {notice}
          </p>
        ) : null}
        {chat.sendError ? (
          <p className="lg-notice lg-notice--error" role="alert">
            Send failed: {chat.sendError.message}{' '}
            <span className="lg-card__path">({chat.sendError.code})</span>
          </p>
        ) : null}
        {attachmentError ? (
          <p className="lg-notice lg-notice--error" role="alert">
            {attachmentError}
          </p>
        ) : null}
        {/* Reply-time Sources from the just-returned send (not yet reloaded). */}
        {!privatePersonal && lastSendSources ? (
          <ChatSources data={lastSendSources} onOpen={openSourceInFiles} />
        ) : null}
        {privatePersonal && privateAttachmentsAvailable === false ? (
          <p className="lg-notice" role="status">
            Private attachments are unavailable on this backend (private_attachments
            capability missing). Shared Team files remain available in Team.
          </p>
        ) : null}
        {!privatePersonal ? (
          <div className="lg-chat__tools">
            <button type="button" className="lg-button" aria-label="Add attachments and materials" aria-expanded={extrasOpen} aria-controls="lg-chat-extras" onClick={() => setExtrasOpen(!extrasOpen)}>+</button>
            {selection.selection.length > 0 && !extrasOpen ? <span>{selection.selection.length} selected material(s) <button type="button" className="lg-link-button" onClick={() => setExtrasOpen(true)}>Review</button></span> : null}
            {!extrasOpen && drafts.drafts.length > 0 ? <span aria-live="polite">{drafts.busy ? 'Storing materials…' : `${drafts.drafts.length} draft file(s)`} <button type="button" className="lg-link-button" onClick={() => setExtrasOpen(true)}>Review</button></span> : null}
            {!extrasOpen && intakeCapabilityChecked && !sharedIntakeV2 && materials.materials.length > 0 ? <span aria-live="polite">{materials.busy ? 'Uploading…' : `${materials.materials.length} upload receipt(s)`} <button type="button" className="lg-link-button" onClick={() => setExtrasOpen(true)}>View uploads</button></span> : null}
          </div>
        ) : null}
        {!privatePersonal ? <div id="lg-chat-extras" hidden={!extrasOpen}>
        {sharedIntakeV2 ? (
          <p className="lg-notice" role="status">
            Files chosen with the paperclip stay local until Send. Intake then runs in the
            background and its receipt appears under the message. Materials below are still
            explicit context, not automated selection.
          </p>
        ) : !intakeCapabilityChecked ? (
          <p className="lg-notice" role="status">
            Checking material intake support before enabling uploads…
          </p>
        ) : (
          <ChatMaterialIntake
            materials={materials.materials}
            busy={materials.busy}
            scopeLabel={scopeLabel}
            canWrite
            notice={materialNotice}
            onUploadFiles={(files) => {
              setMaterialNotice(null)
              void materials.uploadFiles(files, { taskRef: effectiveTaskRef })
            }}
            onRecordLink={(url) => {
              setMaterialNotice(null)
              materials.recordLink(url, { taskRef: effectiveTaskRef }).catch((cause: unknown) => {
                setMaterialNotice(cause instanceof Error ? cause.message : 'Invalid link')
              })
            }}
            onRefresh={(requestId) => void materials.refresh(requestId)}
            onDismiss={materials.dismiss}
          />
        )}
        <ChatSourcePicker
          api={resolvedSourcesApi}
          taskRef={effectiveTaskRef}
          selection={selection.selection}
          atLimit={selection.atLimit}
          onToggle={selection.toggle}
          onRemove={selection.remove}
          onClear={selection.clear}
          disabled={chat.sending}
        />
        <label className="lg-chat__attach">
          <span className="lg-visually-hidden">Reference a file by path</span>
          <input
            type="text"
            className="lg-input"
            placeholder="Attach file path (workspace-relative)…"
            aria-label="Attach file path"
            onChange={handleAddAttachment}
          />
        </label>
        </div> : null}
        <ChatComposer
          value={draft}
          onChange={(value) => {
            dispatch({ type: 'setDraft', key, value })
            if (notice) setNotice(null)
          }}
          onSubmit={handleSubmit}
          scopeLabel={scopeLabel}
          onFilesPicked={handleFilesPicked}
          attachDisabled={
            privatePersonal
              ? privateAttachmentsAvailable !== true
              : sharedIntakeV2 && drafts.busy
          }
          attachDisabledReason={
            privateAttachmentsAvailable === null
              ? 'Checking private attachment support…'
              : 'Private attachments are unavailable on this backend (private_attachments capability missing).'
          }
          disabled={
            chat.sending ||
            (!privatePersonal && sharedIntakeV2 && drafts.busy) ||
            (privatePersonal &&
              privateAttachments.some((item) => item.status === 'uploading'))
          }
          disabledReason={
            !privatePersonal && sharedIntakeV2 && drafts.busy
              ? 'Wait for material intake to finish before sending.'
              : 'Wait for the attachment upload to finish before sending.'
          }
          attachments={
            privatePersonal ? (
              privateAttachments.length > 0 ? (
                <ul className="lg-chat__chip-row" aria-label="Pending attachments">
                  {privateAttachments.map((attachment) => (
                    <li key={attachment.attachmentId} className="lg-chip">
                      <span className="lg-card__path">{attachment.filename}</span>
                      <span
                        className={`lg-chat__attachment-status lg-chat__attachment-status--${attachment.status}`}
                        title={attachment.error ?? undefined}
                      >
                        {attachment.status === 'uploading'
                          ? 'uploading…'
                          : attachment.status === 'failed'
                            ? `not uploaded${attachment.error ? `: ${attachment.error}` : ''}`
                            : 'uploaded'}
                      </span>
                      {attachment.status === 'failed' ? (
                        <button
                          type="button"
                          className="lg-link-button"
                          onClick={() => retryPrivateAttachment(attachment)}
                        >
                          Retry
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="lg-icon-button"
                        aria-label={`Remove attachment ${attachment.filename}`}
                        onClick={() => removePrivateAttachment(attachment)}
                      >
                        <Icon name="close" size={12} />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null
            ) : sharedIntakeV2 ? (
              <>
                <ChatDraftChips
                  drafts={drafts.drafts}
                  onRemove={drafts.remove}
                  disabled={chat.sending || drafts.busy}
                />
                {attachments.length > 0 ? (
                  <ul className="lg-chat__chip-row" aria-label="Pending attachments">
                    {attachments.map((attachment, index) => (
                      <li key={`${attachment.path}-${index}`} className="lg-chip">
                        <span className="lg-card__path">{attachment.path}</span>
                        <button
                          type="button"
                          className="lg-icon-button"
                          aria-label={`Remove attachment ${attachment.path}`}
                          onClick={() =>
                            setAttachments((current) => current.filter((_, i) => i !== index))
                          }
                        >
                          <Icon name="close" size={12} />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : attachments.length > 0 ? (
              <ul className="lg-chat__chip-row" aria-label="Pending attachments">
                {attachments.map((attachment, index) => (
                  <li key={`${attachment.path}-${index}`} className="lg-chip">
                    <span className="lg-card__path">{attachment.path}</span>
                    <button
                      type="button"
                      className="lg-icon-button"
                      aria-label={`Remove attachment ${attachment.path}`}
                      onClick={() =>
                        setAttachments((current) => current.filter((_, i) => i !== index))
                      }
                    >
                      <Icon name="close" size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null
          }
        />
      </footer>
    </section>
  )
}

function privateContextLabel(status: string): string {
  switch (status) {
    case 'included':
      return 'in model context'
    case 'truncated':
      return 'context truncated'
    case 'unsupported_type':
      return 'not read — unsupported type'
    case 'binary_unsupported':
      return 'not read — binary/non-UTF-8'
    case 'too_large':
      return 'not read — over text size limit'
    default:
      return 'not read — unavailable'
  }
}

function guessMediaType(path: string): string | null {
  // Reference-only attachment classification; no bytes leave the browser.

  const lower = path.toLowerCase()
  if (lower.endsWith('.md')) return 'text/markdown'
  if (lower.endsWith('.json')) return 'application/json'
  if (lower.endsWith('.txt')) return 'text/plain'
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
  return null
}
