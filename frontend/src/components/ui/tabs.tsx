import * as React from "react"

import { cn } from "@/lib/utils"

const Tabs = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & {
    value?: string
    onValueChange?: (value: string) => void
  }
>(({ className, value, onValueChange, ...props }, ref) => {
  const [internalValue, setInternalValue] = React.useState(value || "")
  
  const handleValueChange = (newValue: string) => {
    setInternalValue(newValue)
    onValueChange?.(newValue)
  }
  
  return (
    <div
      ref={ref}
      className={cn("w-full", className)}
      {...props}
    >
      <TabsContext.Provider value={{ value: value || internalValue, onValueChange: handleValueChange }}>
        {props.children}
      </TabsContext.Provider>
    </div>
  )
})
Tabs.displayName = "Tabs"

type TabsContextType = {
  value: string
  onValueChange: (value: string) => void
}

const TabsContext = React.createContext<TabsContextType | null>(null)

function useTabs() {
  const context = React.useContext(TabsContext)
  if (!context) {
    throw new Error("useTabs must be used within a Tabs component")
  }
  return context
}

const TabsList = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground",
      className
    )}
    {...props}
  />
))
TabsList.displayName = "TabsList"

const TabsTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    value: string
  }
>(({ className, value, ...props }, ref) => {
  const { value: selectedValue, onValueChange } = useTabs()
  const isSelected = selectedValue === value
  
  return (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={isSelected}
      data-state={isSelected ? "active" : "inactive"}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
        isSelected
          ? "bg-background text-foreground shadow-sm"
          : "hover:bg-background/50 hover:text-foreground",
        className
      )}
      onClick={() => onValueChange(value)}
      {...props}
    />
  )
})
TabsTrigger.displayName = "TabsTrigger"

const TabsContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & {
    value: string
  }
>(({ className, value, ...props }, ref) => {
  const { value: selectedValue } = useTabs()
  const isSelected = selectedValue === value
  
  if (!isSelected) {
    return null
  }
  
  return (
    <div
      ref={ref}
      role="tabpanel"
      data-state={isSelected ? "active" : "inactive"}
      className={cn(
        "mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        className
      )}
      {...props}
    />
  )
})
TabsContent.displayName = "TabsContent"

export { Tabs, TabsList, TabsTrigger, TabsContent }
