"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { FileText, MessageCircle, Mic, Search, Filter, Calendar } from "lucide-react"

interface Conversation {
  id: string
  date: Date
  type: "text" | "voice"
  duration: number
  messageCount: number
  summary: string
  topics: string[]
  mood?: string
}

export default function HistoryPage() {
  const [searchTerm, setSearchTerm] = useState("")
  
  const conversations: Conversation[] = [
    {
      id: "1",
      date: new Date("2024-03-15T10:30:00"),
      type: "text",
      duration: 15,
      messageCount: 24,
      summary: "Discussion sur le stress au travail et les techniques de relaxation",
      topics: ["stress", "travail", "relaxation"],
      mood: "anxieux",
    },
    {
      id: "2",
      date: new Date("2024-03-14T14:15:00"),
      type: "voice",
      duration: 8,
      messageCount: 12,
      summary: "Check-in quotidien et évaluation de l'humeur",
      topics: ["humeur", "sommeil"],
      mood: "neutre",
    },
    {
      id: "3",
      date: new Date("2024-03-13T09:00:00"),
      type: "text",
      duration: 20,
      messageCount: 35,
      summary: "Exploration des objectifs personnels et progression",
      topics: ["objectifs", "progression", "motivation"],
      mood: "positif",
    },
    {
      id: "4",
      date: new Date("2024-03-12T16:45:00"),
      type: "voice",
      duration: 12,
      messageCount: 18,
      summary: "Discussion sur les difficultés de sommeil",
      topics: ["sommeil", "routine", "anxiété"],
      mood: "fatigué",
    },
    {
      id: "5",
      date: new Date("2024-03-11T11:20:00"),
      type: "text",
      duration: 10,
      messageCount: 16,
      summary: "Point sur les techniques de gestion du stress apprises",
      topics: ["stress", "techniques", "pratique"],
      mood: "calme",
    },
  ]

  const filteredConversations = conversations.filter(
    (c) =>
      c.summary.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.topics.some((t) => t.toLowerCase().includes(searchTerm.toLowerCase()))
  )

  const formatDuration = (minutes: number) => {
    if (minutes < 60) {
      return `${minutes} min`
    }
    const hours = Math.floor(minutes / 60)
    const mins = minutes % 60
    return `${hours}h ${mins}min`
  }

  const getTypeIcon = (type: "text" | "voice") => {
    return type === "text" ? (
      <MessageCircle className="h-4 w-4" />
    ) : (
      <Mic className="h-4 w-4" />
    )
  }

  const getMoodColor = (mood?: string) => {
    switch (mood?.toLowerCase()) {
      case "positif":
        return "bg-green-100 text-green-800"
      case "anxieux":
        return "bg-yellow-100 text-yellow-800"
      case "fatigué":
        return "bg-blue-100 text-blue-800"
      case "calme":
        return "bg-purple-100 text-purple-800"
      default:
        return "bg-gray-100 text-gray-800"
    }
  }

  return (
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="border-b p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Historique</h2>
            <p className="text-muted-foreground">
              Retrouvez toutes vos conversations passées
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="border-b p-4">
        <div className="flex gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Rechercher par sujet ou résumé..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button variant="outline">
            <Filter className="mr-2 h-4 w-4" />
            Filtres
          </Button>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 p-6">
        <div className="space-y-4">
          {filteredConversations.map((conversation) => (
            <Card key={conversation.id} className="hover:bg-muted/50 transition-colors cursor-pointer">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                      {getTypeIcon(conversation.type)}
                    </div>
                    <div>
                      <CardTitle className="text-base flex items-center gap-2">
                        {conversation.type === "text" ? "Conversation texte" : "Session vocale"}
                      </CardTitle>
                      <CardDescription className="flex items-center gap-2">
                        <Calendar className="h-3 w-3" />
                        {conversation.date.toLocaleDateString("fr-FR", {
                          weekday: "long",
                          year: "numeric",
                          month: "long",
                          day: "numeric",
                        })}{" "}
                        à {conversation.date.toLocaleTimeString("fr-FR", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="gap-1">
                      {getTypeIcon(conversation.type)}
                      {formatDuration(conversation.duration)}
                    </Badge>
                    {conversation.mood && (
                      <Badge className={getMoodColor(conversation.mood)}>
                        {conversation.mood}
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{conversation.summary}</p>
                <div className="flex items-center justify-between">
                  <div className="flex gap-2">
                    {conversation.topics.map((topic) => (
                      <Badge key={topic} variant="secondary" className="text-xs">
                        #{topic}
                      </Badge>
                    ))}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {conversation.messageCount} messages
                  </div>
                </div>
                <Button variant="ghost" size="sm" className="w-full">
                  <FileText className="mr-2 h-4 w-4" />
                  Voir la conversation complète
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
