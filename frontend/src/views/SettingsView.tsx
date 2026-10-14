import { PlaceholderView } from './PlaceholderView'

/**
 * Settings view (owner: LG-026). LG-011 only provides the bottom nav entry and
 * mount point; model connections, credentials and Test Connection are LG-026
 * over the LG-025 backend.
 */
export function SettingsView() {
  return (
    <PlaceholderView
      viewId="settings"
      ownerTask="LG-026"
      title="Settings"
      summary="Models & Providers, credential configuration and connection tests are not implemented in the shell."
      planned={[
        'Models & Providers using the same Connection entity as Resources',
        'Credential fields submitted once and never echoed back',
        'Layered Test Connection results with real config version/time',
      ]}
    />
  )
}
