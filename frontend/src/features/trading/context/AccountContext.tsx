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

export function AccountProvider({ children }: { children: ReactNode }) {
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)

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
