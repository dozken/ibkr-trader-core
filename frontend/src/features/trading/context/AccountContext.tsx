import { createContext, useContext, useState, ReactNode } from 'react'

interface AccountContextValue {
  selectedAccountId: number | null
  setSelectedAccountId: (id: number | null) => void
  accountParam: string
}

const AccountContext = createContext<AccountContextValue>({
  selectedAccountId: null,
  setSelectedAccountId: () => {},
  accountParam: '',
})

function readStoredAccount(): number | null {
  const raw = localStorage.getItem('selectedAccountId')
  if (raw == null) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

export function AccountProvider({ children }: { children: ReactNode }) {
  const [selectedAccountId, _setSelectedAccountId] = useState<number | null>(readStoredAccount)

  function setSelectedAccountId(id: number | null) {
    _setSelectedAccountId(id)
    if (id != null) localStorage.setItem('selectedAccountId', String(id))
    else localStorage.removeItem('selectedAccountId')
  }

  const accountParam = selectedAccountId != null ? `account_id=${selectedAccountId}` : ''

  return (
    <AccountContext.Provider value={{ selectedAccountId, setSelectedAccountId, accountParam }}>
      {children}
    </AccountContext.Provider>
  )
}

export function useAccount() {
  return useContext(AccountContext)
}
