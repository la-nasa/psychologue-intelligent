"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Bell, Shield, Eye, Volume2, Globe, Key } from "lucide-react"

export default function SettingsPage() {
  const [notifications, setNotifications] = useState({
    email: true,
    push: true,
    sms: false,
    dailyReminder: true,
    weeklyReport: true,
    alertNotifications: true,
  })

  const [privacy, setPrivacy] = useState({
    shareDataWithClinician: true,
    allowAiLearning: false,
    showProgressToClinician: true,
    anonymousAnalytics: true,
  })

  const [accessibility, setAccessibility] = useState({
    highContrast: false,
    largeText: false,
    screenReader: false,
    reducedMotion: false,
  })

  const [voice, setVoice] = useState({
    autoPlayResponses: true,
    voiceSpeed: 1.0,
    voiceVolume: 0.8,
    noiseCancellation: true,
  })

  return (
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="border-b p-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Paramètres</h2>
          <p className="text-muted-foreground">
            Personnalisez votre expérience et gérez vos préférences
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 space-y-6 p-6">
        {/* Notifications */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Bell className="h-5 w-5 text-primary" />
              <CardTitle>Notifications</CardTitle>
            </div>
            <CardDescription>Gérez comment vous recevez les notifications</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Email</Label>
                <p className="text-sm text-muted-foreground">
                  Recevoir des notifications par email
                </p>
              </div>
              <Switch
                checked={notifications.email}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, email: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Push</Label>
                <p className="text-sm text-muted-foreground">
                  Notifications push sur votre appareil
                </p>
              </div>
              <Switch
                checked={notifications.push}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, push: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>SMS</Label>
                <p className="text-sm text-muted-foreground">
                  Alertes importantes par SMS
                </p>
              </div>
              <Switch
                checked={notifications.sms}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, sms: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Rappel quotidien</Label>
                <p className="text-sm text-muted-foreground">
                  Rappel pour votre check-in quotidien
                </p>
              </div>
              <Switch
                checked={notifications.dailyReminder}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, dailyReminder: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Rapport hebdomadaire</Label>
                <p className="text-sm text-muted-foreground">
                  Résumé de votre progression chaque semaine
                </p>
              </div>
              <Switch
                checked={notifications.weeklyReport}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, weeklyReport: checked })
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Privacy */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              <CardTitle>Confidentialité</CardTitle>
            </div>
            <CardDescription>Contrôlez vos données et leur utilisation</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Partager avec le clinicien</Label>
                <p className="text-sm text-muted-foreground">
                  Votre psychologue peut voir vos conversations
                </p>
              </div>
              <Switch
                checked={privacy.shareDataWithClinician}
                onCheckedChange={(checked) =>
                  setPrivacy({ ...privacy, shareDataWithClinician: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Apprentissage IA</Label>
                <p className="text-sm text-muted-foreground">
                  Autoriser l'utilisation anonymisée pour améliorer l'IA
                </p>
              </div>
              <Switch
                checked={privacy.allowAiLearning}
                onCheckedChange={(checked) =>
                  setPrivacy({ ...privacy, allowAiLearning: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Afficher la progression</Label>
                <p className="text-sm text-muted-foreground">
                  Montrer vos objectifs et progrès au clinicien
                </p>
              </div>
              <Switch
                checked={privacy.showProgressToClinician}
                onCheckedChange={(checked) =>
                  setPrivacy({ ...privacy, showProgressToClinician: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Analyses anonymes</Label>
                <p className="text-sm text-muted-foreground">
                  Contribuer aux statistiques d'usage anonymisées
                </p>
              </div>
              <Switch
                checked={privacy.anonymousAnalytics}
                onCheckedChange={(checked) =>
                  setPrivacy({ ...privacy, anonymousAnalytics: checked })
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Accessibility */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Eye className="h-5 w-5 text-primary" />
              <CardTitle>Accessibilité</CardTitle>
            </div>
            <CardDescription>Améliorez l'accessibilité de l'interface</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Contraste élevé</Label>
                <p className="text-sm text-muted-foreground">
                  Augmente le contraste des éléments
                </p>
              </div>
              <Switch
                checked={accessibility.highContrast}
                onCheckedChange={(checked) =>
                  setAccessibility({ ...accessibility, highContrast: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Texte agrandi</Label>
                <p className="text-sm text-muted-foreground">
                  Taille de police plus grande
                </p>
              </div>
              <Switch
                checked={accessibility.largeText}
                onCheckedChange={(checked) =>
                  setAccessibility({ ...accessibility, largeText: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Lecteur d'écran</Label>
                <p className="text-sm text-muted-foreground">
                  Optimisé pour les lecteurs d'écran
                </p>
              </div>
              <Switch
                checked={accessibility.screenReader}
                onCheckedChange={(checked) =>
                  setAccessibility({ ...accessibility, screenReader: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Mouvements réduits</Label>
                <p className="text-sm text-muted-foreground">
                  Diminue les animations
                </p>
              </div>
              <Switch
                checked={accessibility.reducedMotion}
                onCheckedChange={(checked) =>
                  setAccessibility({ ...accessibility, reducedMotion: checked })
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Voice */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Volume2 className="h-5 w-5 text-primary" />
              <CardTitle>Vocal</CardTitle>
            </div>
            <CardDescription>Paramètres des sessions vocales</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Lecture automatique</Label>
                <p className="text-sm text-muted-foreground">
                  Lire automatiquement les réponses de l'IA
                </p>
              </div>
              <Switch
                checked={voice.autoPlayResponses}
                onCheckedChange={(checked) =>
                  setVoice({ ...voice, autoPlayResponses: checked })
                }
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Réduction du bruit</Label>
                <p className="text-sm text-muted-foreground">
                  Filtrer les bruits de fond pendant les appels
                </p>
              </div>
              <Switch
                checked={voice.noiseCancellation}
                onCheckedChange={(checked) =>
                  setVoice({ ...voice, noiseCancellation: checked })
                }
              />
            </div>
          </CardContent>
        </Card>

        {/* Security */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5 text-primary" />
              <CardTitle>Sécurité</CardTitle>
            </div>
            <CardDescription>Gérez la sécurité de votre compte</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button variant="outline" className="w-full justify-start">
              <Key className="mr-2 h-4 w-4" />
              Changer le mot de passe
            </Button>
            <Button variant="outline" className="w-full justify-start">
              <Shield className="mr-2 h-4 w-4" />
              Activer l'authentification à deux facteurs
            </Button>
            <Button variant="outline" className="w-full justify-start">
              <Globe className="mr-2 h-4 w-4" />
              Gérer les sessions actives
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
