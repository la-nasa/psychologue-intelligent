"use client"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { MessageCircle, Mic, Activity, Target } from "lucide-react"

export default function Home() {
  return (
    <div className="flex-1 space-y-8 p-6 pt-6">
      {/* Welcome Section */}
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight">Bonjour</h1>
        <p className="text-muted-foreground">
          Comment vous sentez-vous aujourd&apos;hui ?
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-medium">Commencer une conversation</CardTitle>
            <CardDescription>Discutez avec notre assistant IA</CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" size="lg">
              <MessageCircle className="mr-2 h-5 w-5" />
              Conversation texte
            </Button>
          </CardContent>
        </Card>

        <Card className="col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-medium">Session vocale</CardTitle>
            <CardDescription>Parlez naturellement avec l&apos;IA</CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" variant="outline" size="lg">
              <Mic className="mr-2 h-5 w-5" />
              Conversation vocale
            </Button>
          </CardContent>
        </Card>

        <Card className="col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-medium">Check-in rapide</CardTitle>
            <CardDescription>Évaluez votre humeur du moment</CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" variant="secondary" size="lg">
              <Activity className="mr-2 h-5 w-5" />
              Check-in
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Progress Section */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="h-5 w-5 text-primary" />
              Vos objectifs
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Améliorer le sommeil</span>
                <span className="text-muted-foreground">70%</span>
              </div>
              <Progress value={70} className="h-2" />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Gérer le stress</span>
                <span className="text-muted-foreground">45%</span>
              </div>
              <Progress value={45} className="h-2" />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Routine quotidienne</span>
                <span className="text-muted-foreground">60%</span>
              </div>
              <Progress value={60} className="h-2" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              Votre progression
            </CardTitle>
            <CardDescription>Cette semaine</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Conversations</span>
                <Badge variant="secondary">5 cette semaine</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Check-ins</span>
                <Badge variant="secondary">12 complétés</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Objectifs actifs</span>
                <Badge variant="secondary">3 en cours</Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
